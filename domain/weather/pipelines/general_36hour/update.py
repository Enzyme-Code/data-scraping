import datetime
import os
from dotenv import load_dotenv

from storage import DatabaseFactory
from domain.weather.providers.client import WeatherClient
from domain.weather.pipelines.general_36hour.config import CITY_TO_TICKER
from domain.weather.pipelines.utils import build_postgre_config, write_many
from utils.logger import set_log

load_dotenv()
log = set_log(project_name="weather/forecast_36h")

cfg = build_postgre_config()

def safe_int(val):
    try: return int(val)
    except (ValueError, TypeError): return None

def update():
    log.info("開始執行36小時天氣預報同步排程")
    client = WeatherClient(api_key=os.getenv("WEATHER_API_KEY"))
    
    try:
        raw_response = client.get_rest_data(data_id="F-C0032-001")
        locations = raw_response[0]['records']['location']
    except Exception as e:
        log.error(f"氣象署 API 請求或解析失敗: {e}", exc_info=True)
        return

    db_connector = DatabaseFactory.get_connector(cfg)
    db_connector.connect()
    
    try:
        ticker_rows = db_connector.execute("SELECT id, ticker_code FROM ticker.ticker_info;")
        code_to_id = {
            (row['ticker_code'] if isinstance(row, dict) else row[1]): 
            (row['id'] if isinstance(row, dict) else row[0]) 
            for row in ticker_rows
        }
        
        valid_records = []

        for loc_data in locations:
            city_name = loc_data.get("locationName")
            ticker_code = CITY_TO_TICKER.get(city_name)
            ticker_id = code_to_id.get(ticker_code)
            if not ticker_id: continue

            time_slots = {}
            for element in loc_data.get("weatherElement", []):
                elem_name = element.get("elementName") 
                for t_block in element.get("time", []):
                    st = t_block.get("startTime")
                    et = t_block.get("endTime")
                    if not st: continue

                    slot_key = (st, et)
                    if slot_key not in time_slots:
                        time_slots[slot_key] = {}
                    
                    param = t_block.get("parameter", {})
                    p_name = param.get("parameterName")
                    
                    if elem_name == "Wx":
                        time_slots[slot_key]["wx_text"] = p_name
                    elif elem_name == "CI":
                        time_slots[slot_key]["ci_text"] = p_name
                    elif elem_name == "PoP":
                        time_slots[slot_key]["pop"] = safe_int(p_name)
                    elif elem_name == "MinT":
                        time_slots[slot_key]["min_temp"] = safe_int(p_name)
                    elif elem_name == "MaxT":
                        time_slots[slot_key]["max_temp"] = safe_int(p_name)

            for (st_str, et_str), data in time_slots.items():
                parsed_st = datetime.datetime.strptime(st_str.replace("T", " ").split("+")[0].strip(), "%Y-%m-%d %H:%M:%S")
                parsed_et = datetime.datetime.strptime(et_str.replace("T", " ").split("+")[0].strip(), "%Y-%m-%d %H:%M:%S")
                
                desc = f"{data.get('wx_text', '未知天氣')}。降雨機率 {data.get('pop', 0)}%。溫度攝氏 {data.get('min_temp', 0)} 至 {data.get('max_temp', 0)} 度。體感{data.get('ci_text', '舒適')}。"

                valid_records.append((
                    ticker_id, city_name, parsed_st, parsed_et,
                    data.get("wx_text"), data.get("pop"), data.get("min_temp"), 
                    data.get("max_temp"), data.get("ci_text"), desc
                ))

        if valid_records:
            upsert_sql = """
                INSERT INTO weather.forecast_36hour (
                    ticker_id, county_name, start_time, end_time, wx_text, pop, min_temp, max_temp, ci_text, weather_description
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker_id, county_name, start_time) 
                DO UPDATE SET 
                    end_time = EXCLUDED.end_time,
                    wx_text = EXCLUDED.wx_text,
                    pop = EXCLUDED.pop,
                    min_temp = EXCLUDED.min_temp,
                    max_temp = EXCLUDED.max_temp,
                    ci_text = EXCLUDED.ci_text,
                    weather_description = EXCLUDED.weather_description,
                    updated_at = NOW();
            """
            write_many(db_connector, upsert_sql, valid_records)
            log.info(f"成功同步 {len(valid_records)} 筆36小時縣市預報資料")

    finally:
        db_connector.close()

if __name__ == "__main__":
    update()