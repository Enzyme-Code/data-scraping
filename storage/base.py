from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class DatabaseConnector(ABC):
    def __init__(self, config: Any):
        self.config = config
        
    @abstractmethod
    def connect(self):
        """
        - initialize database connection and pool
        - create connection
        """
        pass

    @abstractmethod
    def execute(self):
        """
        - excute SQL query
        """
        pass
    
    @abstractmethod
    def close(self):
        """
        - close connection or pool to release source
        """
        pass
    
    @abstractmethod
    def is_healthy(self):
        """
        - check database status
        """
        pass