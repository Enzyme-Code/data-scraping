import os
import pandas as pd
import json
from .base import Base

class Uploader(Base):
    def file_upload(self, excel_filename: str):
        current_dir = os.path.dirname(__file__)
        excel_path = os.path.join(current_dir, excel_filename)
        
        if not os.path.exists(excel_path):
            print(f"[ERROR] Source file not found: {excel_path}")
            return

        print(f"[INFO] Syncing configuration from: {excel_path}")
        df = pd.read_excel(excel_path)
        for _, row in df.iterrows():
            ticker_val = row['ticker']
            category_val = row['category']
            zh_name_val = row['name_zh']  # 取得中文名
            en_name_val = row['name_en']  # 取得英文名

            self._ensure_raw_table_exists(category_val)

            # 同時保留 JSONB 格式給未來擴充
            display_names = json.dumps({
                "zh_tw": zh_name_val,
                "en": en_name_val
            }, ensure_ascii=False)

            # 更新 SQL 語句，加入 zh_name 與 en_name
            upsert_query = """
            INSERT INTO ticker.ticker_info (
                ticker_code, zh_name, en_name, display_names, 
                owner, source, category, region, frequency, url, note, is_active
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) 
            ON CONFLICT (ticker_code) 
            DO UPDATE SET 
                zh_name = EXCLUDED.zh_name,
                en_name = EXCLUDED.en_name,
                display_names = EXCLUDED.display_names,
                url = EXCLUDED.url,
                updated_at = NOW();
            """
            params = (
                ticker_val, zh_name_val, en_name_val, display_names,
                row['owner'], row['source'], category_val, row['region'], 
                str(row['frequency']), row['url'], row.get('note', ''), True
            )

            try:
                self.db.execute(upsert_query, params)
                print(f"[SUCCESS] Synced ticker: {ticker_val} ({zh_name_val})")
            except Exception as e:
                print(f"[FAILED] Error processing {ticker_val}: {str(e)}")

if __name__ == "__main__":
    with Uploader() as uploader:
        uploader.file_upload("weather.xlsx")