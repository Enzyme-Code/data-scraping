import datetime
import os
import json
from dotenv import load_dotenv

from storage import DatabaseFactory, PostgreConfig
from domain.weather.providers.client import WeatherClient
from utils.logger import set_log

load_dotenv()
log = set_log(project_name="weather/sync_1week")

# 強制將埠號轉為 int 以符合配置要求
cfg = PostgreConfig(
    host=os.getenv("PG_HOST"),
    port=int(os.getenv("PG_PORT", 5432)),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
    database=os.getenv("DATABASE")
)

TICKER_MAP_1WEEK = {
    "sys.wea.cwa.il.1week": "F-D0047-003", "sys.wea.cwa.ty.1week": "F-D0047-007",
    "sys.wea.cwa.hsh.1week": "F-D0047-011", "sys.wea.cwa.ml.1week": "F-D0047-015",
    "sys.wea.cwa.ch.1week": "F-D0047-019", "sys.wea.cwa.nt.1week": "F-D0047-023",
    "sys.wea.cwa.yl.1week": "F-D0047-027", "sys.wea.cwa.cyh.1week": "F-D0047-031",
    "sys.wea.cwa.pt.1week": "F-D0047-035", "sys.wea.cwa.tt.1week": "F-D0047-039",
    "sys.wea.cwa.hl.1week": "F-D0047-043", "sys.wea.cwa.ph.1week": "F-D0047-047",
    "sys.wea.cwa.kl.1week": "F-D0047-051", "sys.wea.cwa.hsc.1week": "F-D0047-055",
    "sys.wea.cwa.cyc.1week": "F-D0047-059", "sys.wea.cwa.tp.1week": "F-D0047-063",
    "sys.wea.cwa.kh.1week": "F-D0047-067", "sys.wea.cwa.ntpc.1week": "F-D0047-071",
    "sys.wea.cwa.tc.1week": "F-D0047-075", "sys.wea.cwa.tn.1week": "F-D0047-079",
    "sys.wea.cwa.mz.1week": "F-D0047-083", "sys.wea.cwa.km.1week": "F-D0047-087"
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
    """未來1週鄉鎮預報：多接口輪詢 -> 記憶體即時清洗 -> 批次滾動 Upsert"""
    log.info(f"=== 未來一週鄉鎮預報排程開始 (預計輪詢 {len(TICKER_MAP_1WEEK)} 個 CWA 接口) ===")
    client = WeatherClient(api_key=os.getenv("WEATHER_API_KEY"))

    # 1. 初始化資料庫連線
    try:
        db_connector = DatabaseFactory.get_connector(cfg)
        db_connector.connect()
    except Exception as e:
        log.critical(f"基礎建設資料庫連線池初始化失敗: {e}", exc_info=True)
        return

    try:
        # 2. 預先載入 Ticker ID 對照表，將迴圈效能優化至極致
        ticker_rows = db_connector.execute("SELECT id, ticker_code FROM ticker.ticker_info;")
        code_to_id = {
            (row['ticker_code'] if isinstance(row, dict) else row[1]): 
            (row['id'] if isinstance(row, dict) else row[0]) 
            for row in ticker_rows
        }

        valid_records = []
        
        # 3. 展開 API 輪詢大迴圈
        for ticker_code, data_id in TICKER_MAP_1WEEK.items():
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

                # 4. 鄉鎮市區級資料清洗（處理雙層時間軸與複雜元素映射）
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
                            st = t_block.get("StartTime") or t_block.get("startTime")
                            et = t_block.get("EndTime") or t_block.get("endTime")
                            if not st or not et: continue
                            
                            slot_key = (st, et)
                            if slot_key not in time_slots:
                                time_slots[slot_key] = {}
                                
                            values = t_block.get("ElementValue") or t_block.get("elementValue", [])
                            if not values: continue
                            v0 = values[0]
                            
                            # 1週預報專屬的高精準度數據字典匹配
                            if elem_name == "平均溫度":
                                time_slots[slot_key]["avg_temp"] = safe_int(v0.get("Temperature") or v0.get("temperature"))
                            elif elem_name == "平均露點溫度":
                                time_slots[slot_key]["avg_dew_point"] = safe_int(v0.get("DewPoint") or v0.get("dewPoint"))
                            elif elem_name == "最高溫度":
                                time_slots[slot_key]["max_temp"] = safe_int(v0.get("MaxTemperature") or v0.get("maxTemperature"))
                            elif elem_name == "最低溫度":
                                time_slots[slot_key]["min_temp"] = safe_int(v0.get("MinTemperature") or v0.get("minTemperature"))
                            elif elem_name == "最高體感溫度":
                                time_slots[slot_key]["max_apparent_temp"] = safe_int(v0.get("MaxApparentTemperature") or v0.get("maxApparentTemperature"))
                            elif elem_name == "最低體感溫度":
                                time_slots[slot_key]["min_apparent_temp"] = safe_int(v0.get("MinApparentTemperature") or v0.get("minApparentTemperature"))
                            elif elem_name == "最大舒適度指數":
                                time_slots[slot_key]["max_ci_code"] = safe_int(v0.get("MaxComfortIndex") or v0.get("maxComfortIndex"))
                                time_slots[slot_key]["max_ci_text"] = v0.get("MaxComfortIndexDescription") or v0.get("maxComfortIndexDescription", "")
                            elif elem_name == "最小舒適度指數":
                                time_slots[slot_key]["min_ci_code"] = safe_int(v0.get("MinComfortIndex") or v0.get("minComfortIndex"))
                                time_slots[slot_key]["min_ci_text"] = v0.get("MinComfortIndexDescription") or v0.get("minComfortIndexDescription", "")
                            elif elem_name == "平均相對濕度":
                                time_slots[slot_key]["avg_rh"] = safe_int(v0.get("RelativeHumidity") or v0.get("relativeHumidity"))
                            elif elem_name == "風向":
                                time_slots[slot_key]["wind_dir"] = v0.get("WindDirection") or v0.get("windDirection", "")
                            elif elem_name == "風速":
                                time_slots[slot_key]["wind_speed"] = v0.get("WindSpeed") or v0.get("windSpeed", "")
                                time_slots[slot_key]["beaufort"] = safe_int(v0.get("BeaufortScale") or v0.get("beaufortScale"))
                            elif "降雨機率" in elem_name:
                                time_slots[slot_key]["pop"] = safe_int(v0.get("ProbabilityOfPrecipitation") or v0.get("probabilityOfPrecipitation"))
                            elif elem_name == "紫外線指數":
                                time_slots[slot_key]["uvi_code"] = safe_int(v0.get("UVIndex") or v0.get("uvIndex"))
                                time_slots[slot_key]["uvi_text"] = v0.get("UVExposureLevel") or v0.get("uvExposureLevel", "")
                            elif elem_name == "天氣現象":
                                time_slots[slot_key]["wx_text"] = v0.get("Weather") or v0.get("weather", "")
                                time_slots[slot_key]["wx_code"] = safe_int(v0.get("WeatherCode") or v0.get("weatherCode"))
                            elif elem_name == "天氣預報綜合描述":
                                time_slots[slot_key]["weather_desc"] = v0.get("WeatherDescription") or v0.get("weatherDescription", "")

                    # 將暫存的數據清洗轉換後，打包塞入記憶體批次緩衝區
                    for (st_str, et_str), data in time_slots.items():
                        parsed_st = parse_time(st_str)
                        parsed_et = parse_time(et_str)
                        if not parsed_st or not parsed_et: continue

                        valid_records.append((
                            ticker_info_id, geocode, parsed_st, parsed_et, county_name, township_name, lat, lon,
                            data.get("avg_temp"), data.get("avg_dew_point"), data.get("max_temp"), data.get("min_temp"),
                            data.get("max_apparent_temp"), data.get("min_apparent_temp"),
                            data.get("max_ci_code"), data.get("max_ci_text"), data.get("min_ci_code"), data.get("min_ci_text"),
                            data.get("avg_rh"), data.get("wind_dir"), data.get("wind_speed"), data.get("beaufort"),
                            data.get("pop"), data.get("uvi_code"), data.get("uvi_text"),
                            data.get("wx_text"), data.get("wx_code"), data.get("weather_desc")
                        ))
                log.info(f"[解析成功] Ticker: {ticker_code} ({county_name}) 已暫存至記憶體。")

            except Exception as api_err:
                log.error(f"[接口失敗] Ticker: {ticker_code} 請求或解析時發生異常: {api_err}", exc_info=True)
                continue

        # 5. 批次 Upsert 入庫 (data.weather_1week)
        if not valid_records:
            log.warning("本次全台輪詢未轉換出任何 1週預報有效數據，終止寫入。")
            return

        try:
            log.info(f"啟動高防禦批次交易：準備將總計 {len(valid_records)} 筆時段預報同步至 data.weather_1week 表...")
            upsert_sql = """
                INSERT INTO data.weather_1week (
                    ticker_info_id, geocode, start_time, end_time, county_name, township_name, latitude, longitude,
                    avg_temp, avg_dew_point, max_temp, min_temp, max_apparent_temp, min_apparent_temp,
                    max_ci_code, max_ci_text, min_ci_code, min_ci_text, avg_rh, wind_dir, wind_speed,
                    beaufort, pop, uvi_code, uvi_text, wx_text, wx_code, weather_desc
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker_info_id, geocode, start_time, end_time) 
                DO UPDATE SET 
                    county_name = EXCLUDED.county_name,
                    township_name = EXCLUDED.township_name,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    avg_temp = EXCLUDED.avg_temp,
                    avg_dew_point = EXCLUDED.avg_dew_point,
                    max_temp = EXCLUDED.max_temp,
                    min_temp = EXCLUDED.min_temp,
                    max_apparent_temp = EXCLUDED.max_apparent_temp,
                    min_apparent_temp = EXCLUDED.min_apparent_temp,
                    max_ci_code = EXCLUDED.max_ci_code,
                    max_ci_text = EXCLUDED.max_ci_text,
                    min_ci_code = EXCLUDED.min_ci_code,
                    min_ci_text = EXCLUDED.min_ci_text,
                    avg_rh = EXCLUDED.avg_rh,
                    wind_dir = EXCLUDED.wind_dir,
                    wind_speed = EXCLUDED.wind_speed,
                    beaufort = EXCLUDED.beaufort,
                    pop = EXCLUDED.pop,
                    uvi_code = EXCLUDED.uvi_code,
                    uvi_text = EXCLUDED.uvi_text,
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
            log.info(f"=== 滾動更新完畢！全台1週鄉鎮預報成功覆蓋更新 {len(valid_records)} 筆時段數據！ ===")
        except Exception as db_err:
            log.error(f"批次寫入 data.weather_1week 時發生資料庫阻斷異常: {db_err}", exc_info=True)

    finally:
        # 6. 強制回收連線資源，防止卡死
        if hasattr(db_connector, 'close'):
            db_connector.close()
            log.info("[INFO] 資料庫連線池通道已安全回收關閉。")

if __name__ == "__main__":
    update()