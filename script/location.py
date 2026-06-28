import os
from dotenv import load_dotenv
from storage import DatabaseFactory, PostgreConfig
from domain.weather.providers.client import WeatherClient
from utils.logger import set_log

load_dotenv()
log = set_log(project_name="weather/init_locations")

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

def run_init():
    log.info("開始執行全台鄉鎮市地理主檔初始化程序")
    client = WeatherClient(api_key=os.getenv("WEATHER_API_KEY"))
    
    try:
        db_connector = DatabaseFactory.get_connector(cfg)
        db_connector.connect()
    except Exception as e:
        log.critical(f"資料庫連線失敗: {e}")
        return

    location_master_set = {}

    for ticker_code, data_id in TICKER_MAP_1WEEK.items():
        log.info(f"正在下載接口: {data_id}")
        try:
            raw_response = client.get_rest_data(data_id=data_id)
            records_node = raw_response[0].get('records', {})
            locations_list = records_node.get('Locations') or records_node.get('locations', [])
            if not locations_list or not locations_list[0]: continue

            dataset = locations_list[0]
            county_name = dataset.get("LocationsName") or dataset.get("locationsName")
            location_array = dataset.get('Location') or dataset.get('location', [])

            for loc in location_array:
                township_name = loc.get("LocationName") or loc.get("locationName")
                geocode = loc.get("Geocode") or loc.get("geocode")
                lat = float(loc.get("Latitude")) if loc.get("Latitude") else None
                lon = float(loc.get("Longitude")) if loc.get("Longitude") else None

                if geocode and geocode not in location_master_set:
                    # 依據資料表欄位順序打包：geocode, county_name, township_name, longitude (lon), latitude (lat)
                    location_master_set[geocode] = (geocode, county_name, township_name, lon, lat)

        except Exception as err:
            log.error(f"下載或解析地理主檔時發生錯誤 (接口: {data_id}): {err}")
            continue

    if not location_master_set:
        log.warning("未收集到任何鄉鎮地理資訊，終止寫入。")
        db_connector.close()
        return

    try:
        log.info(f"成功收集到共 {len(location_master_set)} 筆全台鄉鎮地理座標主檔，準備批次寫入...")
        
        upsert_sql = """
            INSERT INTO weather.location_info (geocode, county_name, township_name, longitude, latitude)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (geocode) DO UPDATE SET
                county_name = EXCLUDED.county_name,
                township_name = EXCLUDED.township_name,
                longitude = EXCLUDED.longitude,
                latitude = EXCLUDED.latitude
        """
        
        master_list = list(location_master_set.values())
        if hasattr(db_connector, 'executemany'):
            db_connector.executemany(upsert_sql, master_list)
        else:
            for row in master_list:
                db_connector.execute(upsert_sql, row)
                
        log.info("全台鄉鎮市地理主檔初始化成功")
    except Exception as db_err:
        log.error(f"批次寫入維度表時發生資料庫異常: {db_err}", exc_info=True)
    finally:
        db_connector.close()

if __name__ == "__main__":
    run_init()