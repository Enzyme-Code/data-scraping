import os
from dotenv import load_dotenv

from storage import DatabaseFactory, PostgreConfig
from utils.logger import set_log

load_dotenv()
log = set_log(project_name="air/purge_job")

cfg = PostgreConfig(
    host=os.getenv("PG_HOST"),
    port=int(os.getenv("PG_PORT", 5432)),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
    database=os.getenv("DATABASE")
)

def purge_expired_data():
    log.info("啟動過期空氣品質數據清理任務")
    try:
        db_connector = DatabaseFactory.get_connector(cfg)
        db_connector.connect()
    except Exception as e:
        log.critical(f"清理任務連線資料庫失敗: {e}", exc_info=True)
        return

    try:
        purge_general_air_pollution = "DELETE FROM air.general_air_pollution WHERE publishtime < date_trunc('hour', NOW() AT TIME ZONE 'Asia/Taipei');"
        db_connector.execute(purge_general_air_pollution)
        log.info("general_air_pollution 過期即時測站資料切除完畢")

        log.info("過期空氣品質數據清理完畢")

    except Exception as e:
        log.error(f"執行清除任務時發生異常: {e}", exc_info=True)
    finally:
        db_connector.close()

if __name__ == "__main__":
    purge_expired_data()
