import os
from dotenv import load_dotenv
from storage import DatabaseFactory, PostgreConfig

load_dotenv()

class Base:
    def __init__(self):
        config = PostgreConfig(
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            database=os.getenv("DATABASE")
        )
        self.db = DatabaseFactory.get_connector(config)
        self._checked_categories = set()

    def _ensure_raw_table_exists(self, category: str):
        if category in self._checked_categories:
            return
        table_name = f"raw_data.{category}_raw"
        query = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            ticker_info_id INT NOT NULL REFERENCES ticker.ticker_info(id) ON DELETE CASCADE,
            date TIMESTAMP NOT NULL,
            raw_content JSONB NOT NULL,
            fetched_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (ticker_info_id, date)
        );
        CREATE INDEX IF NOT EXISTS idx_{category}_date ON {table_name}(date DESC);
        """
        try:
            self.db.execute(query)
            self._checked_categories.add(category)
            print(f"[INFO] Infrastructure Check: Table {table_name} verified.")
        except Exception as e:
            print(f"[ERROR] Failed to create table {table_name}: {str(e)}")

    def close(self):
        if hasattr(self.db, 'close'):
            self.db.close()
            print("[INFO] Connection closed safely.")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()