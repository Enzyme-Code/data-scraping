import datetime
import os
from dotenv import load_dotenv
from domain.weather.providers.client import WeatherClient
from ingestion.updater import Updater
from utils.logger import set_log 

load_dotenv()

log = set_log(project_name="weather/forecast_36h")

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
    log.info("=== 36小時天氣預報排程開始 ===")
    client = WeatherClient(api_key=os.getenv("WEATHER_API_KEY"))
    
    try:
        log.info("正在向中央氣象署請求 F-C0032-001 原始資料...")
        raw_response = client.get_rest_data(data_id="F-C0032-001")
        log.info("成功取得氣象署原始回傳資料。")
    except Exception as e:
        log.error(f"氣象署 API 連線失敗或 DNS 無法解析！錯誤訊息: {e}", exc_info=True)
        return

    try:
        locations = raw_response[0]['records']['location']
    except (KeyError, IndexError) as e:
        log.error(f"API 資料結構解析失敗（欄位可能被氣象署官方修改）: {e}")
        return

    with Updater() as updater:
        log.info("成功建立資料庫連線，開始推送天氣預報資料...")
        
        success_count = 0
        for loc_data in locations:
            city_name = loc_data.get("locationName")
            ticker_code = CITY_TO_TICKER.get(city_name)
            
            if not ticker_code:
                continue
                
            try:
                start_time_str = loc_data["weatherElement"][0]["time"][0]["startTime"]
                forecast_date = datetime.datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
            except (KeyError, IndexError, ValueError) as e:
                log.error(f"無法解析時間欄位 | 城市: {city_name} | 錯誤原因: {e}")
                continue

            try:
                updater.push_raw_data(
                    ticker_code=ticker_code,
                    date=forecast_date, 
                    raw_data=loc_data 
                )
                log.info(f"[更新成功] {city_name} | 預報基準時間: {forecast_date}")
                success_count += 1
            except Exception as e:
                log.error(f"[更新失敗] {city_name} 寫入資料庫時發生異常: {e}", exc_info=True)

        log.info(f"=== 36小時天氣預報排程結束，共成功更新 {success_count}/{len(locations)} 個縣市 ===")

if __name__ == "__main__":
    update()