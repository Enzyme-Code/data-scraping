import datetime
import os
import json
from dotenv import load_dotenv

from storage import DatabaseFactory, PostgreConfig
from domain.weather.providers.client import WeatherClient
from utils.logger import set_log

load_dotenv()
log = set_log(project_name="weather/sync_36h")

cfg = PostgreConfig(
    host=os.getenv("PG_HOST"),
    port=int(os.getenv("PG_PORT", 5432)),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
    database=os.getenv("DATABASE")
)

CITY_TO_TICKER = {
    "嘉義縣": "sys.wea.cwa.cyh.36h", "新北市": "sys.wea.cwa.ntpc.36h",
    "嘉義市": "sys.wea.cwa.cyc.36h", "新竹縣": "sys.wea.cwa.hsh.36h",
    "新竹市": "sys.wea.cwa.hsc.36h", "臺北市": "sys.wea.cwa.tp.36h",
    "臺南市": "sys.wea.cwa.tn.36h", "宜蘭縣": "sys.wea.cwa.il.36h",
    "苗栗縣": "sys.wea.cwa.ml.36h", "雲林縣": "sys.wea.cwa.yl.36h",
    "花蓮縣": "sys.wea.cwa.hl.36h", "臺中市": "sys.wea.cwa.tc.36h",
    "臺東縣": "sys.wea.cwa.tt.36h", "桃園市": "sys.wea.cwa.ty.36h",
    "南投縣": "sys.wea.cwa.nt.36h", "高雄市": "sys.wea.cwa.kh.36h",
    "金門縣": "sys.wea.cwa.km.36h", "屏東縣": "sys.wea.cwa.pt.36h",
    "基隆市": "sys.wea.cwa.kl.36h", "澎湖縣": "sys.wea.cwa.ph.36h",
    "彰化縣": "sys.wea.cwa.ch.36h", "連江縣": "sys.wea.cwa.mz.36h"
}

def safe_int(val, default=0):
    """安全轉換型態為 int 的防禦函式"""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def _resolve_ticker_id(db_conn, ticker_code: str, cache: dict) -> int:
    """反查 ticker_info 內的主鍵 ID（帶有記憶體快取）"""
    if ticker_code in cache:
        return cache[ticker_code]
    
    query = "SELECT id FROM ticker.ticker_info WHERE ticker_code = %s;"
    results = db_conn.execute(query, (ticker_code,))
    if results and len(results) > 0:
        result = results[0]
        t_id = result['id'] if isinstance(result, dict) else result[0]
        cache[ticker_code] = t_id
        return t_id
    return None

def update():
    """36小時天氣預報：抓取 -> 清洗 -> 批次 Upsert 一體化核心邏輯"""
    log.info("=== 36小時天氣預報：同步與清洗排程開始 ===")
    client = WeatherClient(api_key=os.getenv("WEATHER_API_KEY"))
    
    try:
        log.info("正在向中央氣象署請求 F-C0032-001 原始資料...")
        raw_response = client.get_rest_data(data_id="F-C0032-001")
        log.info("成功取得氣象署原始回傳資料。")
    except Exception as e:
        log.error(f"氣象署 API 連線失敗或 DNS 無法解析！錯誤訊息: {e}", exc_info=True)
        return

    try:
        locations = raw_response[0]['records']['location']
    except (KeyError, IndexError) as e:
        log.error(f"API 資料結構解析失敗（官方可能修改了外層欄位）: {e}")
        return


    db_connector = DatabaseFactory.get_connector(cfg)
    db_connector.connect()
    
    try:
        ticker_cache = {}   
        insert_data_list = []
    
        elem_fields = {"PoP": "pop", "MinT": "min_temp", "MaxT": "max_temp"}

        for loc_data in locations:
            city_name = loc_data.get("locationName")
            ticker_code = CITY_TO_TICKER.get(city_name)
            
            if not ticker_code:
                continue
                
            ticker_id = _resolve_ticker_id(db_connector, ticker_code, ticker_cache)
            if not ticker_id:
                log.warning(f"找不到對應的 Ticker ID，請確認 Excel 是否已同步：{ticker_code} ({city_name})")
                continue

            time_slots = {}
            for element in loc_data.get("weatherElement", []):
                elem_name = element.get("elementName") 
                
                for t_block in element.get("time", []):
                    slot_key = (t_block.get("startTime"), t_block.get("endTime"))
                    if slot_key not in time_slots:
                        time_slots[slot_key] = {}
                    
                    param = t_block.get("parameter", {})
                    p_name = param.get("parameterName")
                    
                    if elem_name == "Wx":
                        time_slots[slot_key]["wx_text"] = p_name
                        time_slots[slot_key]["wx_code"] = safe_int(param.get("parameterValue", 0))
                    elif elem_name == "CI":
                        time_slots[slot_key]["ci_text"] = p_name
                    elif elem_name in elem_fields:
                        time_slots[slot_key][elem_fields[elem_name]] = safe_int(p_name, 0)

            for (start_time, end_time), data in time_slots.items():
                try:
                    start_dt = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
                    end_dt = datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
                except Exception as parse_err:
                    log.error(f"城市 {city_name} 時間格式轉換失敗 ({start_time} / {end_time}): {parse_err}")
                    continue

                insert_data_list.append((
                    ticker_id, start_dt, end_dt, city_name,
                    data.get("wx_text", "未知"), data.get("wx_code", 0), 
                    data.get("pop", 0), data.get("min_temp", 0), 
                    data.get("max_temp", 0), data.get("ci_text", "")
                ))
                
        if not insert_data_list:
            log.warning("本次轉換無任何有效數據，取消寫入程序。")
            return

        try:
            log.info(f"準備批次寫入：正在同步共 {len(insert_data_list)} 筆時段快照至 data.weather_36h 表...")
            
            upsert_sql = """
                INSERT INTO data.weather_36h (
                    ticker_info_id, start_time, end_time, county_name, 
                    wx_text, wx_code, pop, min_temp, max_temp, ci_text
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker_info_id, start_time, end_time) 
                DO UPDATE SET 
                    county_name = EXCLUDED.county_name,
                    wx_text = EXCLUDED.wx_text,
                    wx_code = EXCLUDED.wx_code,
                    pop = EXCLUDED.pop,
                    min_temp = EXCLUDED.min_temp,
                    max_temp = EXCLUDED.max_temp,
                    ci_text = EXCLUDED.ci_text,
                    updated_at = NOW();
            """
            
            if hasattr(db_connector, 'executemany'):
                db_connector.executemany(upsert_sql, insert_data_list)
            else:
                for row in insert_data_list:
                    db_connector.execute(upsert_sql, row)
                    
            log.info(f"=== 同步完成！已成功覆蓋更新 {len(insert_data_list)} 筆最新 data.weather_36h 資料 ===")
        except Exception as db_err:
            log.error(f"寫入 data.weather_36h 正式表時發生資料庫異常: {db_err}", exc_info=True)

    finally:
        if hasattr(db_connector, 'close'):
            db_connector.close()
            log.info("[INFO] 資料庫連線池通道已安全回收關閉。")

if __name__ == "__main__":
    update()