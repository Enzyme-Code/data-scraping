from unittest.mock import MagicMock

from domain.air.providers.client import AirClient


def test_get_air_data_delegates_to_get_data(monkeypatch):
    client = AirClient(api_key="k")
    mock_get_data = MagicMock(return_value={"records": ["ok"]})
    monkeypatch.setattr(client, "_get_data", mock_get_data)

    result = client.get_air_data(data_id="aqx_p_432", limit=10, offset=5)

    mock_get_data.assert_called_once_with(data_id="aqx_p_432", limit=10, offset=5)
    assert result == {"records": ["ok"]}


def test_get_air_data_defaults_limit_and_offset_to_none(monkeypatch):
    client = AirClient(api_key="k")
    mock_get_data = MagicMock(return_value={"records": []})
    monkeypatch.setattr(client, "_get_data", mock_get_data)

    client.get_air_data(data_id="aqx_p_432")

    mock_get_data.assert_called_once_with(data_id="aqx_p_432", limit=None, offset=None)
