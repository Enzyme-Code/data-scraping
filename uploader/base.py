import pandas as pd
import json
import os
from dotenv import load_dotenv
from storage import DatabaseFactory, PostgreConfig

load_dotenv()

class Base:
    def __init__(self, config: PostgreConfig):
        """
        Initialize database connection using the Database Factory.
        """
        self.db = DatabaseFactory.get_connector(config)
        self._checked_categories = set()

    def _ensure_raw_table_exists(self, category: str):
        """
        Dynamically create raw data tables based on Excel 'category' column.
        e.g., category 'weather' will create 'raw_data.weather_raw'
        """
        if category in self._checked_categories:
            return

        table_name = f"raw_data.{category}_raw"
        query = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id BIGSERIAL PRIMARY KEY,
            ticker_id INT REFERENCES ticker.ticker_info(id),
            raw_content JSONB NOT NULL,
            fetched_at TIMESTAMP DEFAULT NOW()
        );
        """
        try:
            self.db.execute(query)
            self._checked_categories.add(category)
            print(f"[INFO] Infrastructure Check: Table {table_name} is verified.")
        except Exception as e:
            print(f"[ERROR] Failed to create table {table_name}: {str(e)}")

    def execute(self, excel_path: str):
        """
        Synchronize Excel configuration to DB.
        Mappings:
        - Excel 'ticker' -> DB 'ticker_code'
        - Excel 'category' -> Used for dynamic table creation
        """
        if not os.path.exists(excel_path):
            print(f"[ERROR] Source file not found: {excel_path}")
            return

        print(f"[INFO] Syncing configuration from: {excel_path}")
        df = pd.read_excel(excel_path)
        
        for _, row in df.iterrows():
            ticker_val = row['ticker']
            category_val = row['category']

            # Ensure raw_data schema environment
            self._ensure_raw_table_exists(category_val)

            # Package Multi-language names
            display_names = json.dumps({
                "zh_tw": row['name_zh'],
                "en": row['name_en']
            }, ensure_ascii=False)

            # UPSERT into ticker.ticker_info
            upsert_query = """
            INSERT INTO ticker.ticker_info (
                ticker_code, display_names, owner, source, category ,region, frequency, url, note, is_active
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) 
            ON CONFLICT (ticker_code) 
            DO UPDATE SET 

                display_names = EXCLUDED.display_names,
                url = EXCLUDED.url,
                frequency = EXCLUDED.frequency,
                owner = EXCLUDED.owner,
                source = EXCLUDED.source,
                category = EXCLUDED.category,
                region = EXCLUDED.region,
                note = EXCLUDED.note,
                updated_at = NOW();
            """
            
            params = (
                ticker_val, 
                display_names, 
                row['owner'], 
                row['source'], 
                category_val,
                row['region'], 
                str(row['frequency']), 
                row['url'], 
                row.get('note', ''),
                True  
            )

            try:
                self.db.execute(upsert_query, params)
                print(f"[SUCCESS] Synced ticker: {ticker_val}")
            except Exception as e:
                print(f"[FAILED] Error processing {ticker_val}: {str(e)}")

        print(f"[FINISH] Excel synchronization completed.")

