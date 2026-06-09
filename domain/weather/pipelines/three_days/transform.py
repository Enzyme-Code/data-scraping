import datetime
import os
from dotenv import load_dotenv

from storage import DatabaseFactory, PostgreConfig
from utils.logger import set_log

load_dotenv()
log = set_log(project_name="weather/transform_3day")

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

cfg = PostgreConfig(
    host = os.getenv("PG_HOST"), port = os.getenv("PG_PORT"),
    user = os.getenv("PG_USER"), password = os.getenv("PG_PASSWORD"),
    database = os.getenv("DATABASE") 
)

def safe_int(val):
    if val is None or str(val).strip() in ("", "-", "—"): return None
    try: return int(float(str(val).strip()))
    except (ValueError, TypeError): return None

def parse_time(t_str):
    if not t_str: return None
    t_str = t_str.replace("T", " ")
    if "+" in t_str: t_str = t_str.split("+")[0]
    return datetime.datetime.strptime(t_str.strip(), "%Y-%m-%d %H:%M:%S")

def transform():
    log.info("=== 未來 3 天鄉鎮預報：資料清洗程序啟動 ===")
    try:
        db_connector = DatabaseFactory.get_connector(cfg)
        db_connector.connect()
    except Exception as e:
        log.critical(f"連線池初始化失敗: {e}", exc_info=True)
        return

    try:
        ticker_rows = db_connector.execute("SELECT id, ticker_code FROM ticker.ticker_info;")
        id_to_ticker = {row['id']: row['ticker_code'] for row in ticker_rows}
        target_ids = [tid for tid, code in id_to_ticker.items() if code in TICKER_MAP_3DAY]
        
        if not target_ids:
            log.warning("系統主表中尚未註冊任何 3天預報的 Ticker 代碼，終止轉換。")
            return

        log.info(f"正在篩選最新批次的未來 3 天原始 JSON...")
        select_sql = """
            SELECT DISTINCT ON (ticker_info_id) ticker_info_id, raw_content 
            FROM raw_data.weather_raw 
            WHERE ticker_info_id = ANY(%s)
            ORDER BY ticker_info_id, fetched_at DESC;
        """
        raw_records = db_connector.execute(select_sql, (target_ids,))
        
        if not raw_records:
            log.warning("原始表中未篩選到任何 3 天預報資料，放棄本次轉換。")
            return

        valid_records = []

        for record in raw_records:
            ticker_info_id = record['ticker_info_id']
            raw_content = record['raw_content']
            datasets = raw_content if isinstance(raw_content, list) else [raw_content]

            for dataset in datasets:
                if not isinstance(dataset, dict): continue
                county_name = dataset.get("LocationsName", "未知縣市")
                
                for loc in dataset.get("Location", []):
                    township_name = loc.get("LocationName")
                    geocode = loc.get("Geocode")
                    lat = float(loc.get("Latitude")) if loc.get("Latitude") else None
                    lon = float(loc.get("Longitude")) if loc.get("Longitude") else None
                    
                    time_slots = {}
                    
                    for element in loc.get("WeatherElement", []):
                        elem_name = element.get("ElementName")
                        
                        for t_block in element.get("Time", []):
                            d_time = t_block.get("DataTime") or t_block.get("StartTime")
                            if not d_time: continue
                            
                            if d_time not in time_slots:
                                time_slots[d_time] = {}
                                
                            values = t_block.get("ElementValue", [])
                            if not values: continue
                            v0 = values[0]
                            
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

                    for d_time, data in time_slots.items():
                        valid_records.append((
                            ticker_info_id, geocode, parse_time(d_time),
                            county_name, township_name, lat, lon,
                            data.get("temp"), data.get("dew_point"), data.get("apparent_temp"),
                            data.get("ci_code"), data.get("ci_text"), data.get("rh"),
                            data.get("wind_dir"), data.get("wind_speed"), data.get("beaufort"),
                            data.get("pop"), data.get("wx_text"), data.get("wx_code"), data.get("weather_desc")
                        ))

        if valid_records:
            log.info(f"正在執行未來 3 天鄉鎮數據滾動覆蓋，總計：{len(valid_records)} 筆...")
            insert_sql = """
                INSERT INTO process_data.weather_3day (
                    ticker_info_id, geocode, data_time, county_name, township_name, latitude, longitude,
                    temp, dew_point, apparent_temp, ci_code, ci_text, rh, wind_dir, wind_speed,
                    beaufort, pop, wx_text, wx_code, weather_desc, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
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
                    created_at = CURRENT_TIMESTAMP;
            """
            if hasattr(db_connector, 'executemany'):
                db_connector.executemany(insert_sql, valid_records)
            else:
                for row in valid_records:
                    db_connector.execute(insert_sql, row)
            log.info(f"=== 未来 3 天鄉鎮預報轉換完畢！成功覆蓋更新 {len(valid_records)} 筆資料。 ===")
        else:
            log.warning("沒有任何有效的資料轉換成功，取消寫入程序。")

    except Exception as e:
        log.error(f"3 天預報清洗程序異常崩潰: {e}", exc_info=True)
    finally:
        db_connector.close()

if __name__ == "__main__":
    transform()