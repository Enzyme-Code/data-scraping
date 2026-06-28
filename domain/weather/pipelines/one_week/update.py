import datetime
import os
from dotenv import load_dotenv

from storage import DatabaseFactory, PostgreConfig
from domain.weather.providers.client import WeatherClient
from utils.logger import set_log

load_dotenv()
log = set_log(project_name="weather/forecast_1week")

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

def parse_time(t_str):
    if not t_str: return None
    return datetime.datetime.strptime(t_str.replace("T", " ").split("+")[0].strip(), "%Y-%m-%d %H:%M:%S")

def update():
    log.info("開始執行1週鄉鎮走勢預報同步排程")
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

        elem_rows = db_connector.execute("SELECT id, element_name FROM weather.element_type;")
        name_to_elem_id = {
            (row['element_name'] if isinstance(row, dict) else row[1]): 
            (row['id'] if isinstance(row, dict) else row[0]) 
            for row in elem_rows
        }

        valid_records = []

        for ticker_code, data_id in TICKER_MAP_1WEEK.items():
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
                        
                        # 過濾不需要的綜合描述與代碼
                        if elem_name in ("天氣預報綜合描述", "ComfortIndexDescription", "最大舒適度指數描述", "最小舒適度指數描述", "WeatherCode", "天氣現象代碼"):
                            continue

                        element_type_id = name_to_elem_id.get(elem_name)
                        if not element_type_id: continue

                        for t_block in element.get('Time', []):
                            st_str = t_block.get("StartTime") or t_block.get("startTime")
                            et_str = t_block.get("EndTime") or t_block.get("endTime")
                            
                            parsed_st = parse_time(st_str)
                            parsed_et = parse_time(et_str)
                            if not parsed_st or not parsed_et: continue

                            values = t_block.get("ElementValue") or t_block.get("elementValue", [])
                            if not values: continue
                            
                            val_dict = values[0]
                            actual_value = next(iter(val_dict.values())) if isinstance(val_dict, dict) else str(val_dict)

                            valid_records.append((
                                ticker_id, location_info_id, parsed_st, parsed_et, element_type_id, str(actual_value)
                            ))

            except Exception as api_err:
                log.error(f"下載或解析 Ticker: {ticker_code} 異常: {api_err}")
                continue

        if valid_records:
            upsert_sql = """
                INSERT INTO weather.forecast_one_week (
                    ticker_id, location_info_id, start_time, end_time, element_type_id, element_value
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker_id, location_info_id, start_time, end_time, element_type_id) 
                DO UPDATE SET 
                    element_value = EXCLUDED.element_value,
                    updated_at = NOW();
            """
            
            batch_size = 1000
            for i in range(0, len(valid_records), batch_size):
                chunk = valid_records[i:i + batch_size]
                if hasattr(db_connector, 'executemany'):
                    db_connector.executemany(upsert_sql, chunk)
                else:
                    for row in chunk: 
                        db_connector.execute(upsert_sql, row)
                        
            log.info(f"成功滾動同步 {len(valid_records)} 筆一週走勢垂直因子數據 (已完成 INT 效能優化分批打包)")

    finally:
        db_connector.close()

if __name__ == "__main__":
    update()