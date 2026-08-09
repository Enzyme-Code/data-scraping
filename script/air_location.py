import os
from dotenv import load_dotenv
from storage import DatabaseFactory, PostgreConfig
from domain.air.providers.client import AirClient
from utils.logger import set_log

load_dotenv()

log = set_log(project_name="air_pollution/init_locations")

cfg = PostgreConfig(
    host=os.getenv("PG_HOST"),
    port=int(os.getenv("PG_PORT", 5432)),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
    database=os.getenv("DATABASE")
)

def run_init():
    log.info("開始執行空氣品質測站地理主檔初始化程序")
    client = AirClient(os.getenv("AIR_API_KEY"))

    try:
        db_connector = DatabaseFactory.get_connector(cfg)
        db_connector.connect()
    except Exception as e:
        log.critical(f"資料庫連線失敗: {e}")
        return

    location_master_set = {}

    try:
        air_data = client.get_air_data("aqx_p_432")
        for record in air_data:
            siteid = record.get("siteid")
            if not siteid or siteid in location_master_set:
                continue

            country = record.get("county")
            sitename = record.get("sitename")
            longitude = float(record.get("longitude")) if record.get("longitude") else None
            latitude = float(record.get("latitude")) if record.get("latitude") else None

            # 依據資料表欄位順序打包：siteid, country, sitename, longitude, latitude
            location_master_set[siteid] = (int(siteid), country, sitename, longitude, latitude)
    except Exception as err:
        log.error(f"下載或解析測站地理主檔時發生錯誤: {err}")
        db_connector.close()
        return

    if not location_master_set:
        log.warning("未收集到任何測站地理資訊，終止寫入。")
        db_connector.close()
        return

    try:
        log.info(f"成功收集到共 {len(location_master_set)} 筆空氣品質測站地理座標主檔，準備批次寫入...")

        upsert_sql = """
            INSERT INTO info.air_pollution_location (siteid, country, sitename, longitude, latitude)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (siteid) DO UPDATE SET
                country = EXCLUDED.country,
                sitename = EXCLUDED.sitename,
                longitude = EXCLUDED.longitude,
                latitude = EXCLUDED.latitude
        """

        master_list = list(location_master_set.values())
        if hasattr(db_connector, 'executemany'):
            db_connector.executemany(upsert_sql, master_list)
        else:
            for row in master_list:
                db_connector.execute(upsert_sql, row)

        log.info("空氣品質測站地理主檔初始化成功")
    except Exception as db_err:
        log.error(f"批次寫入維度表時發生資料庫異常: {db_err}", exc_info=True)
    finally:
        db_connector.close()

if __name__ == "__main__":
    run_init()
