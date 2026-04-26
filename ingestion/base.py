from storage import DatabaseFactory, PostgreConfig

class Base:
    def __init__(self, config: PostgreConfig):
        """
        Initialize database connection using the Database Factory.
        """
        self.db = DatabaseFactory.get_connector(config)
        self._checked_categories = set()

    def _ensure_raw_table_exists(self, category: str):
        """
        Dynamically create raw data tables using a Composite Primary Key.
        - ticker_info_id: References the master ticker_info table. [cite: 88]
        - date: The actual timestamp of the data point. [cite: 88]
        """
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
            print(f"[INFO] Infrastructure Check: Table {table_name} verified (PK: ticker_info_id, date).")
        except Exception as e:
            print(f"[ERROR] Failed to create table {table_name}: {str(e)}")