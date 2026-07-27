import datetime
import os

from dotenv import load_dotenv

from storage import DatabaseFactory
from domain.weather.providers.client import WeatherClient
from domain.weather.pipelines.three_days.config import TICKER_MAP_3DAY
from domain.weather.pipelines.utils import (
    build_postgre_config,
    build_reference_maps,
    get_element_value,
    get_locations,
    get_records_node,
    get_time_blocks,
    get_weather_elements,
    parse_time,
    write_many,
)
from utils.logger import set_log


load_dotenv()
log = set_log(project_name="weather/sync_3day")


cfg = build_postgre_config()


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

    return parse_time(dt_str, log)


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

        write_many(
            db_connector,
            UPSERT_FORECAST_THREE_DAYS_SQL,
            chunk,
            log=log,
            warn_message="db_connector 沒有 executemany，將使用逐筆 execute，速度會比較慢",
        )

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