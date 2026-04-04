from typing import Any
from .base import DatabaseConnector
from .postgres import PostgreSQLConnector
from .config import PostgreConfig

class DatabaseFactory:
    @staticmethod
    def get_connector(config: Any) -> DatabaseConnector:
        """
        The corresponding Connector is automatically generated based on the passed-in Config object.
        """
        if isinstance(config, PostgreConfig):
            return PostgreSQLConnector(config)

        raise ValueError(f"[Factory Error] unsupported db data type: {type(config)}")