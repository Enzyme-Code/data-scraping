import json
from datetime import datetime
from .base import Base

class Updater(Base):
    def __init__(self):
        super().__init__()
        self._ticker_cache = {} 

    def _resolve_ticker(self, ticker_code: str):
        if ticker_code in self._ticker_cache:
            return self._ticker_cache[ticker_code]
        query = "SELECT id, category FROM ticker.ticker_info WHERE ticker_code = %s"
        results = self.db.execute(query, (ticker_code,))
        if results and len(results) > 0:
            result = results[0]
            meta = {"id": result['id'] if isinstance(result, dict) else result[0], "category": result['category'] if isinstance(result, dict) else result[1]}
            self._ticker_cache[ticker_code] = meta
            return meta
        return None

    def push_raw_data(self, ticker_code: str, date: datetime, raw_data: dict):
        meta = self._resolve_ticker(ticker_code)
        if not meta:
            print(f"[ERROR] Ticker '{ticker_code}' not found.")
            return False
        self._ensure_raw_table_exists(meta['category'])
        table_name = f"raw_data.{meta['category']}_raw"
        sql = f"INSERT INTO {table_name} (ticker_info_id, date, raw_content) VALUES (%s, %s, %s) ON CONFLICT (ticker_info_id, date) DO UPDATE SET raw_content = EXCLUDED.raw_content;"
        self.db.execute(sql, (meta['id'], date, json.dumps(raw_data, ensure_ascii=False)))
        return True

"""
with Updater() as client:

use this logic preventing db crush
"""