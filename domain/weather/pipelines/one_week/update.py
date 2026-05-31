import datetime
import os
from dotenv import load_dotenv
from domain.weather.providers.client import WeatherClient
from ingestion.updater import Updater

load_dotenv()

TICKER_MAP_1WEEK = {
    "sys.wea.cwa.il.1week": "F-D0047-003",    # 宜蘭縣
    "sys.wea.cwa.ty.1week": "F-D0047-007",    # 桃園市
    "sys.wea.cwa.hsh.1week": "F-D0047-011",   # 新竹縣
    "sys.wea.cwa.ml.1week": "F-D0047-015",    # 苗栗縣
    "sys.wea.cwa.ch.1week": "F-D0047-019",    # 彰化縣
    "sys.wea.cwa.nt.1week": "F-D0047-023",    # 南投縣
    "sys.wea.cwa.yl.1week": "F-D0047-027",    # 雲林縣
    "sys.wea.cwa.cyh.1week": "F-D0047-031",   # 嘉義縣
    "sys.wea.cwa.pt.1week": "F-D0047-035",    # 屏東縣
    "sys.wea.cwa.tt.1week": "F-D0047-039",    # 台東縣
    "sys.wea.cwa.hl.1week": "F-D0047-043",    # 花蓮縣
    "sys.wea.cwa.ph.1week": "F-D0047-047",    # 澎湖縣
    "sys.wea.cwa.kl.1week": "F-D0047-051",    # 基隆市
    "sys.wea.cwa.hsc.1week": "F-D0047-055",   # 新竹市
    "sys.wea.cwa.cyc.1week": "F-D0047-059",   # 嘉義市
    "sys.wea.cwa.tp.1week": "F-D0047-063",    # 台北市
    "sys.wea.cwa.kh.1week": "F-D0047-067",    # 高雄市
    "sys.wea.cwa.ntpc.1week": "F-D0047-071",  # 新北市
    "sys.wea.cwa.tc.1week": "F-D0047-075",    # 台中市
    "sys.wea.cwa.tn.1week": "F-D0047-079",    # 台南市
    "sys.wea.cwa.mz.1week": "F-D0047-083",    # 連江縣
    "sys.wea.cwa.km.1week": "F-D0047-087"     # 金門縣
}

def update():
    client = WeatherClient(api_key=os.getenv("WEATHER_API_KEY"))

    with Updater() as updater:
        print(f"=== [START] 開始請求未來一週預報 (共 {len(TICKER_MAP_1WEEK)} 個 API) ===")

        for ticker_code, data_id in TICKER_MAP_1WEEK.items():
            print(f"[FETCH] 正在請求 Ticker: {ticker_code} -> API ID: {data_id}")
            
            try:
                raw_response = client.get_rest_data(data_id=data_id)
                
                if not raw_response or 'records' not in raw_response[0]:
                    print(f"[ERROR] API 回傳結構異常: {ticker_code}")
                    continue

                records_node = raw_response[0].get('records', {})
       
                locations_list = records_node.get('Locations') or records_node.get('locations', [])
                if not locations_list:
                    print(f"[ERROR] 找不到 Locations 節點，跳過 {ticker_code}")
                    continue
                
                location_array = locations_list[0].get('Location') or locations_list[0].get('location', [])
                if not location_array:
                    print(f"[ERROR] 找不到 Location 陣列，跳過 {ticker_code}")
                    continue
                
                first_town = location_array[0]
                weather_elements = first_town.get('WeatherElement') or first_town.get('weatherElement', [])
                time_list = weather_elements[0].get('Time') or weather_elements[0].get('time', []) if weather_elements else []
                if not time_list:
                    print(f"[ERROR] 找不到預報時間軸，跳過 {ticker_code}")
                    continue
                
                time_str = time_list[0].get('StartTime') or time_list[0].get('startTime')
                if 'T' in time_str:
                    time_str = time_str.split('+')[0].replace('T', ' ')
                
                forecast_date = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")

                updater.push_raw_data(
                    ticker_code=ticker_code,
                    date=forecast_date,
                    raw_data=locations_list 
                )
                print(f"[SUCCESS] 1week | {ticker_code} 同步成功！時間起點: {forecast_date}")

            except Exception as e:
                print(f"[FAILED] 1week | {ticker_code} 異常: {str(e)}")
                continue

if __name__ == "__main__":
    update()