from .base import AirBase

class AirClient(AirBase):

    def get_air_data(self, data_id: str , limit: int = None, offset: int = None):

        return self._get_data(data_id=data_id, limit=limit, offset=offset)
