import os
from dotenv import load_dotenv
from storage import PostgreConfig
from .base import Base

load_dotenv()

class TickerClient(Base):
    """
    Inherits from Base (the TickerUploadService).
    Provides a cleaner interface for the sync task.
    """
    def run_sync(self, excel_filename: str):
        """
        Main entry point for running the synchronization task.
        """
        excel_path = os.path.join("uploader", "upload_files", excel_filename)
        
        try:
            self.execute(excel_path)
        finally:
            if hasattr(self.db, 'close'):
                self.db.close()
                print(f"[INFO] Connection pool closed for {self.__class__.__name__}")

def start_uploader():
    """
    Standardized entry point to initialize and run the sync process.
    """
    config = PostgreConfig(
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        database=os.getenv("DATABASE")
    )
    
    # Initialize and execute
    service = TickerClient(config)
    service.run_sync(r"uploader\upload_files\weather.xlsx")