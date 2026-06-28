import datetime
import os
from typing import Any

from dotenv import load_dotenv

from storage import DatabaseFactory, PostgreConfig
from domain.weather.providers.client import WeatherClient
from utils.logger import set_log


load_dotenv()
log = set_log(project_name="weather/sync_3day")


cfg = PostgreConfig(
    host=os.getenv("PG_HOST"),
    port=int(os.getenv("PG_PORT", 5432)),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
    database=os.getenv("DATABASE"),
)


TICKER_MAP_3DAY = {
    "sys.wea.cwa.il.3day": "F-D0047-001",
    "sys.wea.cwa.ty.3day": "F-D0047-005",
    "sys.wea.cwa.hsh.3day": "F-D0047-009",
    "sys.wea.cwa.ml.3day": "F-D0047-013",
    "sys.wea.cwa.ch.3day": "F-D0047-017",
    "sys.wea.cwa.nt.3day": "F-D0047-021",
    "sys.wea.cwa.yl.3day": "F-D0047-025",
    "sys.wea.cwa.cyh.3day": "F-D0047-029",
    "sys.wea.cwa.pt.3day": "F-D0047-033",
    "sys.wea.cwa.tt.3day": "F-D0047-037",
    "sys.wea.cwa.hl.3day": "F-D0047-041",
    "sys.wea.cwa.ph.3day": "F-D0047-045",
    "sys.wea.cwa.kl.3day": "F-D0047-049",
    "sys.wea.cwa.hsc.3day": "F-D0047-053",
    "sys.wea.cwa.cyc.3day": "F-D0047-057",
    "sys.wea.cwa.tp.3day": "F-D0047-061",
    "sys.wea.cwa.kh.3day": "F-D0047-065",
    "sys.wea.cwa.ntpc.3day": "F-D0047-069",
    "sys.wea.cwa.tc.3day": "F-D0047-073",
    "sys.wea.cwa.tn.3day": "F-D0047-077",
    "sys.wea.cwa.mz.3day": "F-D0047-081",
    "sys.wea.cwa.km.3day": "F-D0047-085",
}


UPSERT_FORECAST_THREE_DAYS_SQL = """
    INSERT INTO weather.forecast_three_days (
        ticker_id,
        location_info_id,
        data_time,
        element_name,
        element_value
    )
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (ticker_id, location_info_id, data_time, element_name)
    DO UPDATE SET
        element_value = EXCLUDED.element_value,
        updated_at = NOW();
"""


def parse_time(t_str: str | None) -> datetime.datetime | None:
    if not t_str:
        return None

    try:
        normalized = t_str.replace("T", " ").split("+")[0].strip()
        return datetime.datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S")
    except Exception:
        log.warning(f"時間格式解析失敗: {t_str}")
        return None


def row_get(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


def get_records_node(raw_response: Any) -> dict:
    if not raw_response:
        return {}

    if isinstance(raw_response, list):
        first_item = raw_response[0] if raw_response else {}
        if isinstance(first_item, dict):
            return first_item.get("records", {}) or {}
        return {}

    if isinstance(raw_response, dict):
        return raw_response.get("records", {}) or {}

    return {}


def get_locations(records_node: dict) -> list[dict]:
    locations_list = records_node.get("Locations") or records_node.get("locations") or []

    if not locations_list:
        return []

    first_group = locations_list[0] or {}

    return (
        first_group.get("Location")
        or first_group.get("location")
        or []
    )


def get_weather_elements(loc: dict) -> list[dict]:
    return (
        loc.get("WeatherElement")
        or loc.get("weatherElement")
        or []
    )


def get_time_blocks(element: dict) -> list[dict]:
    return (
        element.get("Time")
        or element.get("time")
        or []
    )


def get_element_value(t_block: dict) -> str | None:
    values = (
        t_block.get("ElementValue")
        or t_block.get("elementValue")
        or []
    )

    if not values:
        return None

    first_value = values[0]

    if isinstance(first_value, dict):
        for value in first_value.values():
            if value is not None:
                return str(value)
        return None

    if first_value is not None:
        return str(first_value)

    return None


def get_3day_time(t_block: dict) -> datetime.datetime | None:
    """
    三天預報有些 element 使用 DataTime，
    有些 element 使用 StartTime / EndTime。

    目前 forecast_three_days 只有 data_time，
    所以沒有 DataTime 時，用 StartTime 當 data_time。
    """
    dt_str = (
        t_block.get("DataTime")
        or t_block.get("dataTime")
        or t_block.get("StartTime")
        or t_block.get("startTime")
    )

    return parse_time(dt_str)


def build_reference_maps(db_connector):
    geo_rows = db_connector.execute("""
        SELECT id, geocode
        FROM weather.location_info;
    """)

    geocode_to_id = {
        row_get(row, "geocode", 1): row_get(row, "id", 0)
        for row in geo_rows
        if row_get(row, "geocode", 1)
    }

    ticker_rows = db_connector.execute("""
        SELECT id, ticker_code
        FROM ticker.ticker_info;
    """)

    code_to_id = {
        row_get(row, "ticker_code", 1): row_get(row, "id", 0)
        for row in ticker_rows
        if row_get(row, "ticker_code", 1)
    }

    return geocode_to_id, code_to_id


def fetch_and_normalize_records(
    client: WeatherClient,
    geocode_to_id: dict,
    code_to_id: dict,
) -> list[tuple[int, int, datetime.datetime, str, str]]:
    """
    回傳格式：
    (
        ticker_id,
        location_info_id,
        data_time,
        element_name,
        element_value,
    )

    去重 key：
    (
        ticker_id,
        location_info_id,
        data_time,
        element_name,
    )
    """
    record_map: dict[tuple[int, int, datetime.datetime, str], str] = {}

    total_parsed_count = 0
    total_skipped_count = 0

    for ticker_code, data_id in TICKER_MAP_3DAY.items():
        ticker_id = code_to_id.get(ticker_code)

        if not ticker_id:
            log.warning(f"ticker_info 找不到 ticker_code: {ticker_code}")
            continue

        try:
            log.info(f"開始下載3天預報: ticker_code={ticker_code}, data_id={data_id}")

            raw_response = client.get_rest_data(data_id=data_id)
            records_node = get_records_node(raw_response)
            locations = get_locations(records_node)

            if not locations:
                log.warning(f"CWA response 無 Location: ticker_code={ticker_code}, data_id={data_id}")
                continue

            ticker_parsed_count = 0
            ticker_skipped_count = 0

            for loc in locations:
                geocode = loc.get("Geocode") or loc.get("geocode")
                location_info_id = geocode_to_id.get(geocode)

                if not location_info_id:
                    ticker_skipped_count += 1
                    log.warning(
                        f"location_info 找不到: "
                        f"ticker_code={ticker_code}, data_id={data_id}, geocode={geocode}"
                    )
                    continue

                for element in get_weather_elements(loc):
                    elem_name = element.get("ElementName") or element.get("elementName")

                    if not elem_name:
                        ticker_skipped_count += 1
                        log.warning(
                            f"WeatherElement 無 ElementName: "
                            f"ticker_code={ticker_code}, data_id={data_id}, geocode={geocode}"
                        )
                        continue

                    for t_block in get_time_blocks(element):
                        parsed_dt = get_3day_time(t_block)

                        if not parsed_dt:
                            ticker_skipped_count += 1
                            log.warning(
                                f"3天預報時間解析失敗: "
                                f"ticker_code={ticker_code}, data_id={data_id}, "
                                f"geocode={geocode}, elem_name={elem_name}, "
                                f"raw_time_block={t_block}"
                            )
                            continue

                        actual_value = get_element_value(t_block)

                        if actual_value is None:
                            ticker_skipped_count += 1
                            log.warning(
                                f"3天預報 ElementValue 為空: "
                                f"ticker_code={ticker_code}, data_id={data_id}, "
                                f"geocode={geocode}, elem_name={elem_name}, "
                                f"data_time={parsed_dt}"
                            )
                            continue

                        key = (
                            ticker_id,
                            location_info_id,
                            parsed_dt,
                            elem_name,
                        )

                        record_map[key] = actual_value
                        ticker_parsed_count += 1

            total_parsed_count += ticker_parsed_count
            total_skipped_count += ticker_skipped_count

            log.info(
                f"完成解析3天預報: ticker_code={ticker_code}, "
                f"parsed={ticker_parsed_count}, "
                f"skipped={ticker_skipped_count}, "
                f"目前去重後總筆數={len(record_map)}"
            )

        except Exception as api_err:
            log.error(f"下載或解析 ticker_code={ticker_code}, data_id={data_id} 異常: {api_err}")
            continue

    records = [
        (
            ticker_id,
            location_info_id,
            data_time,
            element_name,
            element_value,
        )
        for (ticker_id, location_info_id, data_time, element_name), element_value
        in record_map.items()
    ]

    log.info(
        f"3天預報資料整理完成: "
        f"parsed={total_parsed_count}, "
        f"skipped={total_skipped_count}, "
        f"deduped={len(records)}"
    )

    return records


def write_records(
    db_connector,
    records: list[tuple[int, int, datetime.datetime, str, str]],
    batch_size: int = 50000,
) -> None:
    if not records:
        log.info("沒有可寫入的3天鄉鎮逐時預報資料")
        return

    total_records = len(records)

    log.info(f"開始寫入3天預報資料: total_records={total_records}")

    for i in range(0, total_records, batch_size):
        chunk = records[i:i + batch_size]
        end_idx = min(i + batch_size, total_records)

        log.info(
            f"正在寫入3天預報資料: "
            f"{end_idx}/{total_records} "
            f"({(end_idx / total_records) * 100:.1f}%)"
        )

        if hasattr(db_connector, "executemany"):
            db_connector.executemany(UPSERT_FORECAST_THREE_DAYS_SQL, chunk)
        else:
            log.warning("db_connector 沒有 executemany，將使用逐筆 execute，速度會比較慢")
            for row in chunk:
                db_connector.execute(UPSERT_FORECAST_THREE_DAYS_SQL, row)

    log.info(f"成功強制同步 {total_records} 筆3天鄉鎮逐時預報資料")


def update():
    log.info("開始執行3天鄉鎮逐時預報同步排程")

    client = WeatherClient(api_key=os.getenv("WEATHER_API_KEY"))

    db_connector = DatabaseFactory.get_connector(cfg)
    db_connector.connect()

    try:
        geocode_to_id, code_to_id = build_reference_maps(db_connector)

        log.info(
            f"reference map 載入完成: "
            f"locations={len(geocode_to_id)}, "
            f"tickers={len(code_to_id)}"
        )

        records = fetch_and_normalize_records(
            client=client,
            geocode_to_id=geocode_to_id,
            code_to_id=code_to_id,
        )

        write_records(
            db_connector=db_connector,
            records=records,
            batch_size=50000,
        )

    finally:
        db_connector.close()
        log.info("3天鄉鎮逐時預報同步排程結束")


if __name__ == "__main__":
    update()