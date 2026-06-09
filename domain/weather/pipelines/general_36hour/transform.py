import datetime
import os
from dotenv import load_dotenv

from storage import DatabaseFactory, PostgreConfig
from utils.logger import set_log

load_dotenv()
log = set_log(project_name="weather/transform_36h")

cfg = PostgreConfig(
    host = os.getenv("PG_HOST"), port = os.getenv("PG_PORT"),
    user = os.getenv("PG_USER"), password = os.getenv("PG_PASSWORD"),
    database = os.getenv("DATABASE") 
)

def safe_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def transform():
    log.info("=== 36小時天氣預報：資料清洗轉換程序啟動 ===")
    try:
        db_connector = DatabaseFactory.get_connector(cfg)
        db_connector.connect()
        log.info("成功初始化 Postgres 連線池，準備執行高階數據操作...")
    except Exception as e:
        log.critical(f"基礎建設連線池初始化失敗: {e}", exc_info=True)
        return

    try:
        log.info("正在從 raw_data.weather_raw 篩選每個縣市『最新一筆』的 36h 原始預報...")
        select_sql = """
            SELECT DISTINCT ON (ticker_info_id) ticker_info_id, raw_content 
            FROM raw_data.weather_raw 
            WHERE ticker_info_id BETWEEN 1 AND 22
            ORDER BY ticker_info_id, fetched_at DESC;
        """
        raw_records = db_connector.execute(select_sql)
        
        if not raw_records:
            log.warning("原始表未撈到任何資料！放棄本次清洗，以保護正式表不被誤清空。")
            return
            
        log.info(f"篩選成功！本次預計處理：{len(raw_records)} 筆縣市原始資料。")

        insert_data_list = []

        for record in raw_records:
            ticker_info_id = record['ticker_info_id']
            raw_content = record['raw_content'] 

            if isinstance(raw_content, dict):
                locations = [raw_content]
            elif isinstance(raw_content, list):
                locations = raw_content
            else:
                continue

            for loc_data in locations:
                if not isinstance(loc_data, dict): continue
                    
                county_name = loc_data.get("locationName")
                if not county_name: continue

                time_slots = {}

                for element in loc_data.get("weatherElement", []):
                    elem_name = element.get("elementName") 
                    
                    for t_block in element.get("time", []):
                        st_str = t_block.get("startTime")
                        et_str = t_block.get("endTime")
                        param = t_block.get("parameter", {})
                        
                        slot_key = (st_str, et_str)
                        if slot_key not in time_slots:
                            time_slots[slot_key] = {}
                        
                        if elem_name == "Wx":
                            time_slots[slot_key]["wx_text"] = param.get("parameterName")
                            time_slots[slot_key]["wx_code"] = safe_int(param.get("parameterValue", 0))
                        elif elem_name == "PoP":
                            time_slots[slot_key]["pop"] = safe_int(param.get("parameterName", 0))
                        elif elem_name == "MinT":
                            time_slots[slot_key]["min_temp"] = safe_int(param.get("parameterName", 0))
                        elif elem_name == "MaxT":
                            time_slots[slot_key]["max_temp"] = safe_int(param.get("parameterName", 0))
                        elif elem_name == "CI":
                            time_slots[slot_key]["ci_text"] = param.get("parameterName")

                for (start_time, end_time), data in time_slots.items():
                    try:
                        start_dt = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
                        end_dt = datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
                    except Exception as parse_err:
                        log.error(f"時間格式解析失敗 ({start_time} / {end_time}): {parse_err}")
                        continue

                    insert_data_list.append((
                        ticker_info_id, start_dt, end_dt, county_name,
                        data.get("wx_text", "未知"), data.get("wx_code", 0), 
                        data.get("pop", 0), data.get("min_temp", 0), 
                        data.get("max_temp", 0), data.get("ci_text", "")
                    ))

        if insert_data_list:
            log.info(f"啟動資料庫交易：準備寫入共 {len(insert_data_list)} 筆時段快照資料...")
            
            upsert_sql = """
                INSERT INTO process_data.weather_36h (
                    ticker_info_id, start_time, end_time, county_name, 
                    wx_text, wx_code, pop, min_temp, max_temp, ci_text, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (ticker_info_id, start_time, end_time) 
                DO UPDATE SET 
                    county_name = EXCLUDED.county_name,
                    wx_text = EXCLUDED.wx_text,
                    wx_code = EXCLUDED.wx_code,
                    pop = EXCLUDED.pop,
                    min_temp = EXCLUDED.min_temp,
                    max_temp = EXCLUDED.max_temp,
                    ci_text = EXCLUDED.ci_text,
                    created_at = CURRENT_TIMESTAMP;
            """
            
            if hasattr(db_connector, 'executemany'):
                db_connector.executemany(upsert_sql, insert_data_list)
            else:
                for row in insert_data_list:
                    db_connector.execute(upsert_sql, row)
                    
            log.info(f"=== 洗完收工！成功無縫更新 {len(insert_data_list)} 筆最新 36h 時段資料！ ===")
        else:
            log.warning("沒有任何有效的資料轉換成功，取消寫入程序。")

    except Exception as e:
        log.error(f"資料清洗過程中發生異常崩潰: {e}", exc_info=True)
    finally:
        db_connector.close()
        log.info("[INFO] 基礎建設連線池已安全回收關閉。")

if __name__ == "__main__":
    transform()