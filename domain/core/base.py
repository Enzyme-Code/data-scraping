import time
from abc import ABC

class Base(ABC):
    def __init__(
        self,
        debug: bool = False,
        max_retries: int = 3,
        retry_delay: int = 2,
        backoff_factor: float = 2.0
    ):
        """
        Initialize retry configurations.
        """
        self.debug = debug
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor

    def _debug(self, msg):
        if self.debug:
            print(f"[DEBUG] {msg}")

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

                self._debug(f"Attempt {retries} failed. Retrying in {delay}s... Error: {e}")
                time.sleep(delay)
                delay *= self.backoff_factor
        return None