import datetime
import os
import json
from dotenv import load_dotenv

from storage import DatabaseFactory, PostgreConfig
from domain.weather.providers.client import WeatherClient
from utils.logger import set_log

load_dotenv()
log = set_log(project_name="weather/sync_3day")

# 配置轉換防禦
cfg = PostgreConfig(
    host=os.getenv("PG_HOST"),
    port=int(os.getenv("PG_PORT", 5432)),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
    database=os.getenv("DATABASE")
)

TICKER_MAP_3DAY = {
    "sys.wea.cwa.il.3day": "F-D0047-001", "sys.wea.cwa.ty.3day": "F-D0047-005",
    "sys.wea.cwa.hsh.3day": "F-D0047-009", "sys.wea.cwa.ml.3day": "F-D0047-013",
    "sys.wea.cwa.ch.3day": "F-D0047-017", "sys.wea.cwa.nt.3day": "F-D0047-021",
    "sys.wea.cwa.yl.3day": "F-D0047-025", "sys.wea.cwa.cyh.3day": "F-D0047-029",
    "sys.wea.cwa.pt.3day": "F-D0047-033", "sys.wea.cwa.tt.3day": "F-D0047-037",
    "sys.wea.cwa.hl.3day": "F-D0047-041", "sys.wea.cwa.ph.3day": "F-D0047-045",
    "sys.wea.cwa.kl.3day": "F-D0047-049", "sys.wea.cwa.hsc.3day": "F-D0047-053",
    "sys.wea.cwa.cyc.3day": "F-D0047-057", "sys.wea.cwa.tp.3day": "F-D0047-061",
    "sys.wea.cwa.kh.3day": "F-D0047-065", "sys.wea.cwa.ntpc.3day": "F-D0047-069",
    "sys.wea.cwa.tc.3day": "F-D0047-073", "sys.wea.cwa.tn.3day": "F-D0047-077",
    "sys.wea.cwa.mz.3day": "F-D0047-081", "sys.wea.cwa.km.3day": "F-D0047-085"
}

def safe_int(val):
    if val is None or str(val).strip() in ("", "-", "—"): return None
    try: return int(float(str(val).strip()))
    except (ValueError, TypeError): return None

def parse_time(t_str):
    if not t_str: return None
    t_str = t_str.replace("T", " ")
    if "+" in t_str: t_str = t_str.split("+")[0]
    return datetime.datetime.strptime(t_str.strip(), "%Y-%m-%d %H:%M:%S")

def update():
    """未來3天鄉鎮預報：多API輪詢 -> 記憶體即時清洗 -> 批次滾動 Upsert"""
    log.info(f"=== 未來三天鄉鎮預報排程開始 (預計輪詢 {len(TICKER_MAP_3DAY)} 個 CWA 接口) ===")
    client = WeatherClient(api_key=os.getenv("WEATHER_API_KEY"))

    # 1. 初始化資料庫連線
    try:
        db_connector = DatabaseFactory.get_connector(cfg)
        db_connector.connect()
    except Exception as e:
        log.critical(f"基礎建設資料庫連線池初始化失敗: {e}", exc_info=True)
        return

    try:
        # 2. 預先預載 Ticker ID 對照表，徹底優化效能
        ticker_rows = db_connector.execute("SELECT id, ticker_code FROM ticker.ticker_info;")
        code_to_id = {
            (row['ticker_code'] if isinstance(row, dict) else row[1]): 
            (row['id'] if isinstance(row, dict) else row[0]) 
            for row in ticker_rows
        }

        valid_records = []
        
        # 3. 展開 API 輪詢大迴圈
        for ticker_code, data_id in TICKER_MAP_3DAY.items():
            ticker_info_id = code_to_id.get(ticker_code)
            if not ticker_info_id:
                log.warning(f"主表中尚未註冊 Ticker: {ticker_code}，跳過此接口。")
                continue

            log.info(f"[輪詢中] Ticker: {ticker_code} -> API ID: {data_id}")
            try:
                raw_response = client.get_rest_data(data_id=data_id)
                if not raw_response or 'records' not in raw_response[0]:
                    log.error(f"API 回傳結構異常，缺少 records 節點 | Ticker: {ticker_code}")
                    continue

                records_node = raw_response[0].get('records', {})
                locations_list = records_node.get('Locations') or records_node.get('locations', [])
                if not locations_list or not locations_list[0]: continue

                dataset = locations_list[0]
                county_name = dataset.get("LocationsName") or dataset.get("locationsName", "未知縣市")
                location_array = dataset.get('Location') or dataset.get('location', [])

                # 4. 鄉鎮級資料清洗
                for loc in location_array:
                    township_name = loc.get("LocationName") or loc.get("locationName")
                    geocode = loc.get("Geocode") or loc.get("geocode")
                    lat = float(loc.get("Latitude")) if loc.get("Latitude") else None
                    lon = float(loc.get("Longitude")) if loc.get("Longitude") else None
                    
                    time_slots = {}
                    weather_elements = loc.get('WeatherElement') or loc.get('weatherElement', [])

                    for element in weather_elements:
                        elem_name = element.get("ElementName") or element.get("elementName")
                        time_list = element.get('Time') or element.get('time', [])
                        
                        for t_block in time_list:
                            d_time = t_block.get("DataTime") or t_block.get("dataTime") or t_block.get("StartTime") or t_block.get("startTime")
                            if not d_time: continue
                            
                            if d_time not in time_slots:
                                time_slots[d_time] = {}
                                
                            values = t_block.get("ElementValue") or t_block.get("elementValue", [])
                            if not values: continue
                            v0 = values[0]
                            
                            # 簡潔高精確度欄位比對機制
                            if elem_name == "溫度":
                                time_slots[d_time]["temp"] = safe_int(v0.get("Temperature"))
                            elif elem_name == "露點溫度":
                                time_slots[d_time]["dew_point"] = safe_int(v0.get("DewPoint"))
                            elif elem_name == "體感溫度":
                                time_slots[d_time]["apparent_temp"] = safe_int(v0.get("ApparentTemperature"))
                            elif elem_name == "相對濕度":
                                time_slots[d_time]["rh"] = safe_int(v0.get("RelativeHumidity"))
                            elif elem_name == "舒適度指數":
                                time_slots[d_time]["ci_code"] = safe_int(v0.get("ComfortIndex"))
                                time_slots[d_time]["ci_text"] = v0.get("ComfortIndexDescription", "")
                            elif elem_name == "風速":
                                time_slots[d_time]["wind_speed"] = v0.get("WindSpeed", "")
                                time_slots[d_time]["beaufort"] = safe_int(v0.get("BeaufortScale"))
                            elif elem_name == "風向":
                                time_slots[d_time]["wind_dir"] = v0.get("WindDirection", "")
                            elif "降雨機率" in elem_name:
                                time_slots[d_time]["pop"] = safe_int(v0.get("ProbabilityOfPrecipitation"))
                            elif elem_name == "天氣現象":
                                time_slots[d_time]["wx_text"] = v0.get("Weather", "")
                                time_slots[d_time]["wx_code"] = safe_int(v0.get("WeatherCode"))
                            elif elem_name == "天氣預報綜合描述":
                                time_slots[d_time]["weather_desc"] = v0.get("WeatherDescription", "")

                    # 打包成標準 Tuple 元組放入記憶體批次清單
                    for d_time, data in time_slots.items():
                        parsed_dt = parse_time(d_time)
                        if not parsed_dt: continue

                        valid_records.append((
                            ticker_info_id, geocode, parsed_dt, county_name, township_name, lat, lon,
                            data.get("temp"), data.get("dew_point"), data.get("apparent_temp"),
                            data.get("ci_code"), data.get("ci_text"), data.get("rh"),
                            data.get("wind_dir"), data.get("wind_speed"), data.get("beaufort"),
                            data.get("pop"), data.get("wx_text"), data.get("wx_code"), data.get("weather_desc")
                        ))
                log.info(f"[解析成功] Ticker: {ticker_code} ({county_name}) 已暫存至記憶體緩衝區。")

            except Exception as api_err:
                log.error(f"[接口失敗] Ticker: {ticker_code} 請求或解析時發生異常: {api_err}", exc_info=True)
                continue

        # 5. 批次 Upsert 入庫 (data.weather_3day)
        if not valid_records:
            log.warning("本次全台輪詢未轉換出任何有效數據，終止寫入。")
            return

        try:
            log.info(f"啟動高防禦交易：準備將總計 {len(valid_records)} 筆時段預報寫入 data.weather_3day...")
            upsert_sql = """
                INSERT INTO data.weather_3day (
                    ticker_info_id, geocode, data_time, county_name, township_name, latitude, longitude,
                    temp, dew_point, apparent_temp, ci_code, ci_text, rh, wind_dir, wind_speed,
                    beaufort, pop, wx_text, wx_code, weather_desc
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker_info_id, geocode, data_time) 
                DO UPDATE SET 
                    county_name = EXCLUDED.county_name,
                    township_name = EXCLUDED.township_name,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    temp = EXCLUDED.temp,
                    dew_point = EXCLUDED.dew_point,
                    apparent_temp = EXCLUDED.apparent_temp,
                    ci_code = EXCLUDED.ci_code,
                    ci_text = EXCLUDED.ci_text,
                    rh = EXCLUDED.rh,
                    wind_dir = EXCLUDED.wind_dir,
                    wind_speed = EXCLUDED.wind_speed,
                    beaufort = EXCLUDED.beaufort,
                    pop = EXCLUDED.pop,
                    wx_text = EXCLUDED.wx_text,
                    wx_code = EXCLUDED.wx_code,
                    weather_desc = EXCLUDED.weather_desc,
                    updated_at = NOW();
            """
            
            if hasattr(db_connector, 'executemany'):
                db_connector.executemany(upsert_sql, valid_records)
            else:
                for row in valid_records:
                    db_connector.execute(upsert_sql, row)
            log.info(f"=== 滾動更新完畢！全台鄉鎮預報成功覆蓋更新 {len(valid_records)} 筆時段數據！ ===")
        except Exception as db_err:
            log.error(f"批次寫入 data.weather_3day 時發生資料庫阻斷異常: {db_err}", exc_info=True)

    finally:
        # 6. 強制善後保護
        if hasattr(db_connector, 'close'):
            db_connector.close()
            log.info("[INFO] 資料庫連線池通道已安全回收關閉。")

if __name__ == "__main__":
    update()