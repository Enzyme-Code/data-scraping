import datetime
import os
from dotenv import load_dotenv

from storage import DatabaseFactory, PostgreConfig
from utils.logger import set_log

load_dotenv()
log = set_log(project_name="weather/transform_1week")

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
    log.info("=== 未來 1 週鄉鎮預報：資料清洗程序啟動 ===")
    try:
        db_connector = DatabaseFactory.get_connector(cfg)
        db_connector.connect()
    except Exception as e:
        log.critical(f"連線池初始化失敗: {e}", exc_info=True)
        return

    try:
        ticker_rows = db_connector.execute("SELECT id, ticker_code FROM ticker.ticker_info;")
        id_to_ticker = {row['id']: row['ticker_code'] for row in ticker_rows}
        target_ids = [tid for tid, code in id_to_ticker.items() if code in TICKER_MAP_1WEEK]
        
        if not target_ids:
            log.warning("系統主表中尚未註冊任何 1週預報的 Ticker 代碼，終止轉換。")
            return

        log.info(f"正在篩選最新批次的未來 1 週原始 JSON...")
        select_sql = """
            SELECT DISTINCT ON (ticker_info_id) ticker_info_id, raw_content 
            FROM raw_data.weather_raw 
            WHERE ticker_info_id = ANY(%s)
            ORDER BY ticker_info_id, fetched_at DESC;
        """
        raw_records = db_connector.execute(select_sql, (target_ids,))
        
        if not raw_records:
            log.warning("原始表中未篩選到任何 1 週預報資料，放棄本次轉換。")
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
                            st = t_block.get("StartTime")
                            et = t_block.get("EndTime")
                            if not st or not et: continue
                            
                            slot_key = (st, et)
                            if slot_key not in time_slots:
                                time_slots[slot_key] = {}
                                
                            values = t_block.get("ElementValue", [])
                            if not values: continue
                            v0 = values[0]
                            
                            if elem_name == "平均溫度":
                                time_slots[slot_key]["avg_temp"] = safe_int(v0.get("Temperature"))
                            elif elem_name == "平均露點溫度":
                                time_slots[slot_key]["avg_dew_point"] = safe_int(v0.get("DewPoint"))
                            elif elem_name == "最高溫度":
                                time_slots[slot_key]["max_temp"] = safe_int(v0.get("MaxTemperature"))
                            elif elem_name == "最低溫度":
                                time_slots[slot_key]["min_temp"] = safe_int(v0.get("MinTemperature"))
                            elif elem_name == "最高體感溫度":
                                time_slots[slot_key]["max_apparent_temp"] = safe_int(v0.get("MaxApparentTemperature"))
                            elif elem_name == "最低體感溫度":
                                time_slots[slot_key]["min_apparent_temp"] = safe_int(v0.get("MinApparentTemperature"))
                            elif elem_name == "最大舒適度指數":
                                time_slots[slot_key]["max_ci_code"] = safe_int(v0.get("MaxComfortIndex"))
                                time_slots[slot_key]["max_ci_text"] = v0.get("MaxComfortIndexDescription", "")
                            elif elem_name == "最小舒適度指數":
                                time_slots[slot_key]["min_ci_code"] = safe_int(v0.get("MinComfortIndex"))
                                time_slots[slot_key]["min_ci_text"] = v0.get("MinComfortIndexDescription", "")
                            elif elem_name == "平均相對濕度":
                                time_slots[slot_key]["avg_rh"] = safe_int(v0.get("RelativeHumidity"))
                            elif elem_name == "風向":
                                time_slots[slot_key]["wind_dir"] = v0.get("WindDirection", "")
                            elif elem_name == "風速":
                                time_slots[slot_key]["wind_speed"] = v0.get("WindSpeed", "")
                                time_slots[slot_key]["beaufort"] = safe_int(v0.get("BeaufortScale"))
                            elif "降雨機率" in elem_name:
                                time_slots[slot_key]["pop"] = safe_int(v0.get("ProbabilityOfPrecipitation"))
                            elif elem_name == "紫外線指數":
                                time_slots[slot_key]["uvi_code"] = safe_int(v0.get("UVIndex"))
                                time_slots[slot_key]["uvi_text"] = v0.get("UVExposureLevel", "")
                            elif elem_name == "天氣現象":
                                time_slots[slot_key]["wx_text"] = v0.get("Weather", "")
                                time_slots[slot_key]["wx_code"] = safe_int(v0.get("WeatherCode"))
                            elif elem_name == "天氣預報綜合描述":
                                time_slots[slot_key]["weather_desc"] = v0.get("WeatherDescription", "")

                    for (st_str, et_str), data in time_slots.items():
                        valid_records.append((
                            ticker_info_id, geocode, parse_time(st_str), parse_time(et_str),
                            county_name, township_name, lat, lon,
                            data.get("avg_temp"), data.get("avg_dew_point"), data.get("max_temp"), data.get("min_temp"),
                            data.get("max_apparent_temp"), data.get("min_apparent_temp"),
                            data.get("max_ci_code"), data.get("max_ci_text"), data.get("min_ci_code"), data.get("min_ci_text"),
                            data.get("avg_rh"), data.get("wind_dir"), data.get("wind_speed"), data.get("beaufort"),
                            data.get("pop"), data.get("uvi_code"), data.get("uvi_text"),
                            data.get("wx_text"), data.get("wx_code"), data.get("weather_desc")
                        ))

        if valid_records:
            log.info(f"正在執行未來 1 週鄉鎮數據滾動覆蓋，總計：{len(valid_records)} 筆...")
            insert_sql = """
                INSERT INTO process_data.weather_1week (
                    ticker_info_id, geocode, start_time, end_time, county_name, township_name, latitude, longitude,
                    avg_temp, avg_dew_point, max_temp, min_temp, max_apparent_temp, min_apparent_temp,
                    max_ci_code, max_ci_text, min_ci_code, min_ci_text, avg_rh, wind_dir, wind_speed,
                    beaufort, pop, uvi_code, uvi_text, wx_text, wx_code, weather_desc, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
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
                    created_at = CURRENT_TIMESTAMP;
            """
            if hasattr(db_connector, 'executemany'):
                db_connector.executemany(insert_sql, valid_records)
            else:
                for row in valid_records:
                    db_connector.execute(insert_sql, row)
            log.info(f"=== 未来 1 週鄉鎮預報轉換完畢！成功覆蓋更新 {len(valid_records)} 筆資料。 ===")
        else:
            log.warning("沒有任何有效的資料轉換成功，取消寫入程序。")

    except Exception as e:
        log.error(f"1 週預報清洗程序異常崩潰: {e}", exc_info=True)
    finally:
        db_connector.close()

if __name__ == "__main__":
    transform()