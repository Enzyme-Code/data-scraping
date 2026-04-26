import os
import pandas as pd
import json
from dotenv import load_dotenv
from .base import Base
from storage import PostgreConfig 

load_dotenv() 

class Uploader(Base):
    def file_upload(self, excel_filename: str):
        """
        Synchronize Excel configuration to the database.
        """
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

            self._ensure_raw_table_exists(category_val)

            display_names = json.dumps({
                "zh_tw": row['name_zh'],
                "en": row['name_en']
            }, ensure_ascii=False)

            upsert_query = """
            INSERT INTO ticker.ticker_info (
                ticker_code, display_names, owner, source, category, region, frequency, url, note, is_active
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) 
            ON CONFLICT (ticker_code) 
            DO UPDATE SET 
                display_names = EXCLUDED.display_names,
                url = EXCLUDED.url,
                frequency = EXCLUDED.frequency,
                updated_at = NOW();
            """
            params = (ticker_val, display_names, row['owner'], row['source'], category_val,
                      row['region'], str(row['frequency']), row['url'], row.get('note', ''), True)

            try:
                self.db.execute(upsert_query, params)
                print(f"[SUCCESS] Synced ticker: {ticker_val}")
            except Exception as e:
                print(f"[FAILED] Error processing {ticker_val}: {str(e)}")

        print(f"[FINISH] Excel synchronization completed.")
        if hasattr(self.db, 'close'):
            self.db.close()
            print(f"[INFO] Connection closed for TickerUploader")

if __name__ == "__main__":
    config = PostgreConfig(
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        database=os.getenv("DATABASE")
    )
    
    uploader = Uploader(config)
    uploader.file_upload("weather.xlsx") # type file name under ingestion