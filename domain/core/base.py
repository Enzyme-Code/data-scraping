import time
from abc import ABC, abstractmethod
from typing import List, Dict, Any

class Base(ABC):
    def __init__(
        self, 
        max_retries: int = 3, 
        retry_delay: int = 2, 
        backoff_factor: float = 2.0
    ):
        """
        Initialize retry configurations.
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor

    def _retry(self, func, *args, **kwargs):
        """
        Generic retry engine using instance parameters.
        """
        retries = 0
        delay = self.retry_delay
        
        while retries <= self.max_retries: 
            try:
                return func(*args, **kwargs)
            except Exception as e:
                retries += 1
                if retries > self.max_retries:
                    raise e
                
                print(f"DEBUG: Attempt {retries} failed. Retrying in {delay}s... Error: {e}")
                time.sleep(delay)
                delay *= self.backoff_factor
        return None

    @abstractmethod
    def _fetch(self) -> List[Dict[str, Any]]:
        """
        Fetch data as a list of dictionaries for JSONB compatibility.
        """
        pass