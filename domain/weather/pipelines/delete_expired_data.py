import os
from dotenv import load_dotenv

from storage import DatabaseFactory, PostgreConfig
from utils.logger import set_log

load_dotenv()
log = set_log(project_name="weather/purge_job")

cfg = PostgreConfig(
    host=os.getenv("PG_HOST"),
    port=int(os.getenv("PG_PORT", 5432)),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
    database=os.getenv("DATABASE")
)

def purge_expired_data():
    log.info("啟動過期天氣預報數據清理任務")
    try:
        db_connector = DatabaseFactory.get_connector(cfg)
        db_connector.connect()
    except Exception as e:
        log.critical(f"清理任務連線資料庫失敗: {e}", exc_info=True)
        return

    try:
        purge_36h = "DELETE FROM weather.forecast_36hour WHERE end_time < (NOW() AT TIME ZONE 'Asia/Taipei' - INTERVAL '1 hour');"
        db_connector.execute(purge_36h)
        log.info("forecast_36hour 過期歷史時段切除完畢")

        purge_3day = "DELETE FROM weather.forecast_three_days WHERE data_time < (NOW() AT TIME ZONE 'Asia/Taipei' - INTERVAL '1 hour');"
        db_connector.execute(purge_3day)
        log.info("forecast_three_days 過期歷史觀測點切除完畢")

        purge_1week = "DELETE FROM weather.forecast_one_week WHERE end_time < (NOW() AT TIME ZONE 'Asia/Taipei' - INTERVAL '1 hour');"
        db_connector.execute(purge_1week)
        log.info("forecast_one_week 過期歷史長週期區間切除完畢")

        log.info("過期預報數據清理完畢")

    except Exception as e:
        log.error(f"執行清除任務時發生異常: {e}", exc_info=True)
    finally:
        db_connector.close()

if __name__ == "__main__":
    purge_expired_data()