import datetime
import os
from typing import Any

from storage import PostgreConfig


def build_postgre_config() -> PostgreConfig:
    return PostgreConfig(
        host=os.getenv("PG_HOST"),
        port=int(os.getenv("PG_PORT", 5432)),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        database=os.getenv("DATABASE"),
    )


def row_get(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


def parse_time(t_str: str | None, log=None) -> datetime.datetime | None:
    if not t_str:
        return None

    try:
        normalized = t_str.replace("T", " ").split("+")[0].strip()
        return datetime.datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S")
    except Exception:
        if log:
            log.warning(f"時間格式解析失敗: {t_str}")
        return None


def get_records_node(raw_response: Any) -> dict:
    if not raw_response:
        return {}

    if isinstance(raw_response, list):
        first_item = raw_response[0] if raw_response else {}
        if isinstance(first_item, dict):
            return first_item.get("records", {}) or {}
        return {}

    if isinstance(raw_response, dict):
        return raw_response.get("records", {}) or {}

    return {}


def get_locations(records_node: dict) -> list[dict]:
    locations_list = records_node.get("Locations") or records_node.get("locations") or []

    if not locations_list:
        return []

    first_group = locations_list[0] or {}

    return (
        first_group.get("Location")
        or first_group.get("location")
        or []
    )


def get_weather_elements(loc: dict) -> list[dict]:
    return (
        loc.get("WeatherElement")
        or loc.get("weatherElement")
        or []
    )


def get_time_blocks(element: dict) -> list[dict]:
    return (
        element.get("Time")
        or element.get("time")
        or []
    )


def get_element_value(t_block: dict) -> str | None:
    values = (
        t_block.get("ElementValue")
        or t_block.get("elementValue")
        or []
    )

    if not values:
        return None

    first_value = values[0]

    if isinstance(first_value, dict):
        for value in first_value.values():
            if value is not None:
                return str(value)
        return None

    if first_value is not None:
        return str(first_value)

    return None


def build_reference_maps(db_connector):
    geo_rows = db_connector.execute("""
        SELECT id, geocode
        FROM weather.location_info;
    """)

    geocode_to_id = {
        row_get(row, "geocode", 1): row_get(row, "id", 0)
        for row in geo_rows
        if row_get(row, "geocode", 1)
    }

    ticker_rows = db_connector.execute("""
        SELECT id, ticker_code
        FROM ticker.ticker_info;
    """)

    code_to_id = {
        row_get(row, "ticker_code", 1): row_get(row, "id", 0)
        for row in ticker_rows
        if row_get(row, "ticker_code", 1)
    }

    return geocode_to_id, code_to_id


def write_many(db_connector, query: str, params_seq, log=None, warn_message: str | None = None) -> None:
    if hasattr(db_connector, "executemany"):
        db_connector.executemany(query, params_seq)
    else:
        if log and warn_message:
            log.warning(warn_message)
        for row in params_seq:
            db_connector.execute(query, row)
