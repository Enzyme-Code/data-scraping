import os
from dotenv import load_dotenv

from storage import DatabaseFactory, PostgreConfig
from domain.air.providers.client import AirClient
from utils.logger import set_log

load_dotenv()

log = set_log(project_name="air/general_air_pollution")

cfg = PostgreConfig(
    host=os.getenv("PG_HOST"),
    port=int(os.getenv("PG_PORT", 5432)),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
    database=os.getenv("DATABASE")
)

DATA_ID = "aqx_p_432"

FIELD_TO_COLUMN = {
    "pm2.5": "pm2_5",
    "pm2.5_avg": "pm2_5_avg",
}

VALUE_COLUMNS = [
    "aqi", "pollutant", "status", "so2", "co", "o3", "o3_8hr", "pm10",
    "pm2_5", "no2", "nox", "no", "wind_speed", "wind_direc", "co_8hr",
    "pm2_5_avg", "pm10_avg", "so2_avg",
]

def safe_int(val):
    try:
        return int(float(val)) if val not in (None, "") else None
    except (ValueError, TypeError):
        return None

def safe_float(val):
    try:
        return float(val) if val not in (None, "") else None
    except (ValueError, TypeError):
        return None

def normalize_record(record):
    normalized = dict(record)
    for api_key, column in FIELD_TO_COLUMN.items():
        if api_key in normalized:
            normalized[column] = normalized.pop(api_key)
    return normalized

def build_site_to_ticker(db_connector):
    """
    ticker_info.zh_name for air stations is "空氣品質 | 測站 | {sitename}",
    where {sitename} matches the API's own "sitename" field exactly.
    """
    ticker_rows = db_connector.execute(
        "SELECT id, zh_name FROM ticker.ticker_info WHERE category = 'air';"
    )
    site_to_ticker = {}
    for row in ticker_rows:
        ticker_id = row["id"] if isinstance(row, dict) else row[0]
        zh_name = row["zh_name"] if isinstance(row, dict) else row[1]
        if not zh_name:
            continue
        sitename = zh_name.split("|")[-1].strip()
        site_to_ticker[sitename] = ticker_id
    return site_to_ticker

def update():
    log.info("開始執行空氣品質即時測站資料同步排程")
    client = AirClient(os.getenv("AIR_API_KEY"))

    try:
        air_data = client.get_air_data(DATA_ID)
    except Exception as e:
        log.error(f"MOENV 空氣品質 API 請求失敗: {e}", exc_info=True)
        return

    db_connector = DatabaseFactory.get_connector(cfg)
    db_connector.connect()

    try:
        site_to_ticker = build_site_to_ticker(db_connector)

        valid_records = []
        for record in air_data:
            sitename = record.get("sitename")
            siteid = safe_int(record.get("siteid"))
            ticker_id = site_to_ticker.get(sitename)

            if not siteid or not ticker_id:
                log.warning(f"找不到測站對應的 ticker_id 或 site_id: {sitename}")
                continue

            normalized = normalize_record(record)

            row = [ticker_id, siteid, normalized.get("publishtime")]
            for column in VALUE_COLUMNS:
                value = normalized.get(column)
                if column in ("pollutant", "status"):
                    row.append(value or None)
                elif column == "pm10":
                    row.append(safe_int(value))
                else:
                    row.append(safe_float(value))
            valid_records.append(tuple(row))

        if not valid_records:
            log.warning("沒有可寫入的空氣品質資料")
            return

        columns_sql = ", ".join(["ticker_id", "site_id", "publishtime"] + VALUE_COLUMNS)
        placeholders_sql = ", ".join(["%s"] * (3 + len(VALUE_COLUMNS)))
        update_sql = ", ".join(f"{column} = EXCLUDED.{column}" for column in VALUE_COLUMNS)
        existing_cols_sql = ", ".join(f"t.{column}" for column in VALUE_COLUMNS)
        excluded_cols_sql = ", ".join(f"EXCLUDED.{column}" for column in VALUE_COLUMNS)

        upsert_sql = f"""
            INSERT INTO air.general_air_pollution AS t ({columns_sql})
            VALUES ({placeholders_sql})
            ON CONFLICT (ticker_id, site_id, publishtime) DO UPDATE SET
                {update_sql},
                update_at = CURRENT_TIMESTAMP
            WHERE ({existing_cols_sql}) IS DISTINCT FROM ({excluded_cols_sql});
        """

        if hasattr(db_connector, "executemany"):
            db_connector.executemany(upsert_sql, valid_records)
        else:
            for row in valid_records:
                db_connector.execute(upsert_sql, row)

        log.info(f"成功同步 {len(valid_records)} 筆空氣品質即時資料")
    except Exception as e:
        log.error(f"寫入空氣品質資料時發生錯誤: {e}", exc_info=True)
    finally:
        db_connector.close()

if __name__ == "__main__":
    update()
