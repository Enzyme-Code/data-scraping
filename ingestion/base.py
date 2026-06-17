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

    def close(self):
        if hasattr(self.db, 'close'):
            self.db.close()
            print("[INFO] Connection closed safely.")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()