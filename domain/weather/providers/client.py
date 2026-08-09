from .base import WeatherBase

class WeatherClient(WeatherBase):
    
    def get_rest_data(self, data_id: str, location_name: str = None):
        
        return self._get_rest_data(data_id=data_id, location_name=location_name)
