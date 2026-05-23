from .base import Base

import os
from dotenv import load_dotenv

class Client(Base):
    
    def get_rest_data(self, data_id: str, location_name: str = None):
        
        return self._get_rest_data(data_id=data_id, location_name=location_name)
    
if __name__ == "__main__":
    load_dotenv()
    client = Client(api_key=os.getenv("WEATHER_API_KEY"))
    data = client.get_rest_data(data_id="F-C0032-001")
    print(data)
