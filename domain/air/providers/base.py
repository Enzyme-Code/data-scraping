import os
import requests
from typing import List, Dict, Any

from domain.core import Handler
from utils.date import to_iso_date

class AirBase(Handler):
    def __init__(
        self,
        api_key: str = None,
        max_retries: int = 3,
        retry_delay: int = 2,
        backoff_factor: float = 2.0
    ):
        """
        Initialize the MOENV Air Quality Provider Client with optional API Key injection.
        """
        super().__init__(max_retries=max_retries, retry_delay=retry_delay, backoff_factor=backoff_factor)

        self.api_key = api_key or os.getenv("AIR_API_KEY")
        self.base_url = "https://data.moenv.gov.tw/api/v2"

    def _fetch(self, data_id: str, limit: int = None, offset: int = None) -> List[Dict[str, Any]]:
        """
        Private worker method executing the actual REST request.
        """
        url = f"{self.base_url}/{data_id}"
        params = {
            "api_key": self.api_key,
            "format": "JSON"
        }
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset

        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        return self._normalize_dates(response.json())

    _DATE_KEY_HINTS = ("date", "time")

    def _normalize_dates(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Auto-detect date/time-like fields by key name (different datasets use
        different names, e.g. monitordate vs publishtime) and normalize the
        date portion to ISO (YYYY-MM-DD), regardless of the raw format the
        API returned it in. Any existing time-of-day is preserved.
        """
        for record in records:
            for key, value in record.items():
                if any(hint in key.lower() for hint in self._DATE_KEY_HINTS):
                    cleaned = to_iso_date(value)
                    if cleaned is not None:
                        record[key] = cleaned
        return records

    def _get_data(self, data_id: str, limit: int = None, offset: int = None) -> List[Dict[str, Any]]:
        """
        Public entry point to fetch air quality datasets.
        Protected by the generic retry mechanism.
        """
        return self._retry(self._fetch, data_id, limit=limit, offset=offset)
