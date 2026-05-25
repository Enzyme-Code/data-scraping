import os
import requests
from typing import List, Dict, Any, Tuple, Optional
from domain.core import Handler

class WeatherBase(Handler):
    def __init__(
        self, 
        api_key: str = None, 
        max_retries: int = 3, 
        retry_delay: int = 2, 
        backoff_factor: float = 2.0
    ):
        """
        Initialize the CWA Provider Client with optional API Key injection.
        """
        super().__init__(max_retries, retry_delay, backoff_factor)
        
        self.api_key = api_key or os.getenv("CWA_API_KEY")
        self.rest_base_url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"
        self.file_base_url = "https://opendata.cwa.gov.tw/fileapi/v1/opendataapi"

    def _fetch(self) -> List[Dict[str, Any]]:
        """
        Default implementation serving as a data structure blueprint.
        Acts as an empty shell since this class utilizes specific multi-worker methods.
        """
        return []


    def _fetch_rest(self, data_id: str, location_name: str = None) -> List[Dict[str, Any]]:
        """
        Private worker method executing the actual REST request.
        """
        url = f"{self.rest_base_url}/{data_id}"
        params = {
            "Authorization": self.api_key,
            "format": "JSON"
        }
        if location_name:
            params["locationName"] = location_name
            
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        return [response.json()]

    def _fetch_file(self, data_id: str, last_etag: str = None) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Private worker method executing file download and checking for HTTP 304 cache status.
        """
        url = f"{self.file_base_url}/{data_id}"
        params = {
            "Authorization": self.api_key,
            "format": "JSON"
        }
        headers = {}
        if last_etag:
            headers["If-None-Match"] = last_etag
            
        response = requests.get(url, params=params, headers=headers, timeout=25, verify=False)
        
        if response.status_code == 304:
            return [], last_etag
            
        response.raise_for_status()
        new_etag = response.headers.get("ETag")
        return [response.json()], new_etag

    def _fetch_history(self, data_id: str, station_id: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        Private worker method executing historical parameterized requests.
        """
        url = f"{self.rest_base_url}/{data_id}"
        params = {
            "Authorization": self.api_key,
            "stationId": station_id,
            "start": start_date,
            "end": end_date,
            "format": "JSON"
        }
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        return [response.json()]



    def _get_rest_data(self, data_id: str, location_name: str = None) -> List[Dict[str, Any]]:
        """
        Public entry point to fetch real-time or forecast rest datastore API.
        Protected by the generic retry mechanism.
        """
        return self._retry(self._fetch_rest, data_id, location_name=location_name)

    def _get_file_data(self, data_id: str, last_etag: str = None) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Public entry point to download full open data files with ETag cache control.
        """
        result = self._retry(self._fetch_file, data_id, last_etag)
        if result is None:
            return [], last_etag
        return result

    def _get_history_data(self, data_id: str, station_id: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        Public entry point to fetch historical climate data sets.
        """
        return self._retry(self._fetch_history, data_id, station_id, start_date, end_date)
    
