import datetime
import os
from typing import Any

from dotenv import load_dotenv

from storage import DatabaseFactory, PostgreConfig
from domain.weather.providers.client import WeatherClient
from utils.logger import set_log


load_dotenv()
log = set_log(project_name="weather/forecast_1week")


cfg = PostgreConfig(
    host=os.getenv("PG_HOST"),
    port=int(os.getenv("PG_PORT", 5432)),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
    database=os.getenv("DATABASE"),
)


TICKER_MAP_1WEEK = {
    "sys.wea.cwa.il.1week": "F-D0047-003",
    "sys.wea.cwa.ty.1week": "F-D0047-007",
    "sys.wea.cwa.hsh.1week": "F-D0047-011",
    "sys.wea.cwa.ml.1week": "F-D0047-015",
    "sys.wea.cwa.ch.1week": "F-D0047-019",
    "sys.wea.cwa.nt.1week": "F-D0047-023",
    "sys.wea.cwa.yl.1week": "F-D0047-027",
    "sys.wea.cwa.cyh.1week": "F-D0047-031",
    "sys.wea.cwa.pt.1week": "F-D0047-035",
    "sys.wea.cwa.tt.1week": "F-D0047-039",
    "sys.wea.cwa.hl.1week": "F-D0047-043",
    "sys.wea.cwa.ph.1week": "F-D0047-047",
    "sys.wea.cwa.kl.1week": "F-D0047-051",
    "sys.wea.cwa.hsc.1week": "F-D0047-055",
    "sys.wea.cwa.cyc.1week": "F-D0047-059",
    "sys.wea.cwa.tp.1week": "F-D0047-063",
    "sys.wea.cwa.kh.1week": "F-D0047-067",
    "sys.wea.cwa.ntpc.1week": "F-D0047-071",
    "sys.wea.cwa.tc.1week": "F-D0047-075",
    "sys.wea.cwa.tn.1week": "F-D0047-079",
    "sys.wea.cwa.mz.1week": "F-D0047-083",
    "sys.wea.cwa.km.1week": "F-D0047-087",
}


UPSERT_FORECAST_ONE_WEEK_SQL = """
    INSERT INTO weather.forecast_one_week (
        ticker_id,
        location_info_id,
        start_time,
        end_time,
        element_name,
        element_value
    )
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (ticker_id, location_info_id, start_time, end_time, element_name)
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
) -> list[tuple[int, int, datetime.datetime, datetime.datetime, str, str]]:
    """
    回傳格式：
    (
        ticker_id,
        location_info_id,
        start_time,
        end_time,
        element_name,
        element_value,
    )

    去重 key：
    (
        ticker_id,
        location_info_id,
        start_time,
        end_time,
        element_name,
    )
    """
    record_map: dict[tuple[int, int, datetime.datetime, datetime.datetime, str], str] = {}

    total_parsed_count = 0
    total_skipped_count = 0

    for ticker_code, data_id in TICKER_MAP_1WEEK.items():
        ticker_id = code_to_id.get(ticker_code)

        if not ticker_id:
            log.warning(f"ticker_info 找不到 ticker_code: {ticker_code}")
            continue

        try:
            log.info(f"開始下載1週預報: ticker_code={ticker_code}, data_id={data_id}")

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
                        st_str = t_block.get("StartTime") or t_block.get("startTime")
                        et_str = t_block.get("EndTime") or t_block.get("endTime")

                        parsed_st = parse_time(st_str)
                        parsed_et = parse_time(et_str)

                        if not parsed_st or not parsed_et:
                            ticker_skipped_count += 1
                            log.warning(
                                f"1週預報時間解析失敗: "
                                f"ticker_code={ticker_code}, data_id={data_id}, "
                                f"geocode={geocode}, elem_name={elem_name}, "
                                f"raw_time_block={t_block}"
                            )
                            continue

                        actual_value = get_element_value(t_block)

                        if actual_value is None:
                            ticker_skipped_count += 1
                            log.warning(
                                f"1週預報 ElementValue 為空: "
                                f"ticker_code={ticker_code}, data_id={data_id}, "
                                f"geocode={geocode}, elem_name={elem_name}, "
                                f"start_time={parsed_st}, end_time={parsed_et}"
                            )
                            continue

                        key = (
                            ticker_id,
                            location_info_id,
                            parsed_st,
                            parsed_et,
                            elem_name,
                        )

                        record_map[key] = actual_value
                        ticker_parsed_count += 1

            total_parsed_count += ticker_parsed_count
            total_skipped_count += ticker_skipped_count

            log.info(
                f"完成解析1週預報: ticker_code={ticker_code}, "
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
            start_time,
            end_time,
            element_name,
            element_value,
        )
        for (ticker_id, location_info_id, start_time, end_time, element_name), element_value
        in record_map.items()
    ]

    log.info(
        f"1週預報資料整理完成: "
        f"parsed={total_parsed_count}, "
        f"skipped={total_skipped_count}, "
        f"deduped={len(records)}"
    )

    return records


def write_records(
    db_connector,
    records: list[tuple[int, int, datetime.datetime, datetime.datetime, str, str]],
    batch_size: int = 50000,
) -> None:
    if not records:
        log.info("沒有可寫入的1週鄉鎮走勢預報資料")
        return

    total_records = len(records)

    log.info(f"開始寫入1週預報資料: total_records={total_records}")

    for i in range(0, total_records, batch_size):
        chunk = records[i:i + batch_size]
        end_idx = min(i + batch_size, total_records)

        log.info(
            f"正在寫入1週預報資料: "
            f"{end_idx}/{total_records} "
            f"({(end_idx / total_records) * 100:.1f}%)"
        )

        if hasattr(db_connector, "executemany"):
            db_connector.executemany(UPSERT_FORECAST_ONE_WEEK_SQL, chunk)
        else:
            log.warning("db_connector 沒有 executemany，將使用逐筆 execute，速度會比較慢")
            for row in chunk:
                db_connector.execute(UPSERT_FORECAST_ONE_WEEK_SQL, row)

    log.info(f"成功強制同步 {total_records} 筆1週鄉鎮走勢預報資料")


def update():
    log.info("開始執行1週鄉鎮走勢預報同步排程")

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
        log.info("1週鄉鎮走勢預報同步排程結束")


if __name__ == "__main__":
    update()