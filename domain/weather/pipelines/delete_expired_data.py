import os
from dotenv import load_dotenv

from storage import DatabaseFactory, PostgreConfig
from utils.logger import set_log

load_dotenv()
log = set_log(project_name="weather/purge_job")

cfg = PostgreConfig(
    host = os.getenv("PG_HOST"), port = os.getenv("PG_PORT"),
    user = os.getenv("PG_USER"), password = os.getenv("PG_PASSWORD"),
    database = os.getenv("DATABASE") 
)

def purge_expired_data():
    log.info("=== 啟動全自動化過期天氣預報數據清理任務 ===")
    try:
        db_connector = DatabaseFactory.get_connector(cfg)
        db_connector.connect()
    except Exception as e:
        log.critical(f"清理任務連線資料庫失敗: {e}", exc_info=True)
        return

    try:
        purge_36h = "DELETE FROM data.weather_36h WHERE end_time < (NOW() AT TIME ZONE 'Asia/Taipei' - INTERVAL '1 hour');"
        db_connector.execute(purge_36h)
        log.info("[1/3] weather_36h 過期歷史時段切除完畢 (含 1 小時寬限期)。")

        purge_3day = "DELETE FROM data.weather_3day WHERE data_time < (NOW() AT TIME ZONE 'Asia/Taipei' - INTERVAL '1 hour');"
        db_connector.execute(purge_3day)
        log.info("[2/3] weather_3day 過期歷史觀測點切除完畢 (含 1 小時寬限期)。")

        purge_1week = "DELETE FROM data.weather_1week WHERE end_time < (NOW() AT TIME ZONE 'Asia/Taipei' - INTERVAL '1 hour');"
        db_connector.execute(purge_1week)
        log.info("[3/3] weather_1week 過期歷史長週期區間切除完畢 (含 1 小時寬限期)。")

        log.info("=== 清理完畢 ===")

    except Exception as e:
        log.error(f"執行清除任務時發生異常: {e}", exc_info=True)
    finally:
        db_connector.close()
        log.info("[INFO] 清理任務連線池安全關閉。")

if __name__ == "__main__":
    purge_expired_data()