import datetime
import os
from dotenv import load_dotenv

from storage import DatabaseFactory, PostgreConfig
from domain.weather.providers.client import WeatherClient
from utils.logger import set_log

load_dotenv()
log = set_log(project_name="weather/sync_3day")

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

def parse_time(t_str):
    if not t_str: return None
    return datetime.datetime.strptime(t_str.replace("T", " ").split("+")[0].strip(), "%Y-%m-%d %H:%M:%S")

def update():
    log.info("開始執行3天鄉鎮逐時預報同步排程")
    client = WeatherClient(api_key=os.getenv("WEATHER_API_KEY"))

    db_connector = DatabaseFactory.get_connector(cfg)
    db_connector.connect()

    try:
        geo_rows = db_connector.execute("SELECT id, geocode FROM weather.location_info;")
        geocode_to_id = {
            (row['geocode'] if isinstance(row, dict) else row[1]): 
            (row['id'] if isinstance(row, dict) else row[0]) 
            for row in geo_rows
        }

        ticker_rows = db_connector.execute("SELECT id, ticker_code FROM ticker.ticker_info;")
        code_to_id = {
            (row['ticker_code'] if isinstance(row, dict) else row[1]): 
            (row['id'] if isinstance(row, dict) else row[0]) 
            for row in ticker_rows
        }

        valid_records = []

        for ticker_code, data_id in TICKER_MAP_3DAY.items():
            ticker_id = code_to_id.get(ticker_code)
            if not ticker_id: continue

            try:
                raw_response = client.get_rest_data(data_id=data_id)
                records_node = raw_response[0].get('records', {})
                locations_list = records_node.get('Locations') or records_node.get('locations', [])
                if not locations_list or not locations_list[0]: continue

                for loc in locations_list[0].get('Location', []):
                    geocode = loc.get("Geocode") or loc.get("geocode")
                    location_info_id = geocode_to_id.get(geocode)
                    if not location_info_id: continue

                    for element in loc.get('WeatherElement', []):
                        elem_name = element.get("ElementName") or element.get("elementName")
                        
                        # 過濾掉不需要存的綜合描述
                        if elem_name in ("天氣預報綜合描述", "ComfortIndexDescription", "舒適度指數描述"):
                            continue

                        for t_block in element.get('Time', []):
                            dt_str = t_block.get("DataTime") or t_block.get("dataTime")
                            parsed_dt = parse_time(dt_str)
                            if not parsed_dt: continue

                            values = t_block.get("ElementValue") or t_block.get("elementValue", [])
                            if not values: continue
                            
                            # 氣象署的數值通常在第一個 key，或者直接取第一個 element 的 value 轉換成字串
                            val_dict = values[0]
                            actual_value = next(iter(val_dict.values())) if isinstance(val_dict, dict) else str(val_dict)

                            valid_records.append((
                                ticker_id, location_info_id, parsed_dt, elem_name, str(actual_value)
                            ))

            except Exception as api_err:
                log.error(f"下載或解析 Ticker: {ticker_code} 異常: {api_err}")
                continue

        if valid_records:
            upsert_sql = """
                INSERT INTO weather.forecast_three_days (
                    ticker_id, location_info_id, data_time, element_name, element_value
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (ticker_id, location_info_id, data_time, element_name) 
                DO UPDATE SET 
                    element_value = EXCLUDED.element_value,
                    updated_at = NOW();
            """
            if hasattr(db_connector, 'executemany'):
                db_connector.executemany(upsert_sql, valid_records)
            else:
                for row in valid_records: 
                    db_connector.execute(upsert_sql, row)
            log.info(f"成功滾動同步 {len(valid_records)} 筆逐時垂直因子數據")

    finally:
        db_connector.close()

if __name__ == "__main__":
    update()