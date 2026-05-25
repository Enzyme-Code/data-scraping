import datetime
import os
from dotenv import load_dotenv
from domain.weather.providers.client import WeatherClient
from ingestion.updater import Updater

load_dotenv()

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

def update():
    client = WeatherClient(api_key=os.getenv("WEATHER_API_KEY"))
    raw_response = client.get_rest_data(data_id="F-C0032-001")

    try:
        locations = raw_response[0]['records']['location']
    except (KeyError, IndexError) as e:
        print(f"[ERROR] API 資料結構解析失敗: {e}")
        return

    with Updater() as updater:
        print("--- 開始推送天氣預報資料至資料庫 ---")
        
        for loc_data in locations:
            city_name = loc_data.get("locationName")
            ticker_code = CITY_TO_TICKER.get(city_name)
            
            if not ticker_code:
                continue
            try:
                start_time_str = loc_data["weatherElement"][0]["time"][0]["startTime"]
                forecast_date = datetime.datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
            except (KeyError, IndexError, ValueError):
                print(f"[ERROR] 無法解析時間: {city_name}")
                continue

            updater.push_raw_data(
                ticker_code=ticker_code,
                date=forecast_date, 
                raw_data=loc_data 
            )
            print(f"[SUCCESS] {city_name} | {forecast_date} | 已更新")

if __name__ == "__main__":
    update()