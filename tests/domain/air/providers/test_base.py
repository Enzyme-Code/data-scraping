from unittest.mock import MagicMock

import pytest

from domain.air.providers.base import AirBase


@pytest.fixture(autouse=True)
def no_real_env(monkeypatch):
    monkeypatch.delenv("AIR_API_KEY", raising=False)


class TestInit:
    def test_uses_explicit_api_key(self):
        base = AirBase(api_key="explicit-key")
        assert base.api_key == "explicit-key"

    def test_falls_back_to_env_var_when_not_given(self, monkeypatch):
        monkeypatch.setenv("AIR_API_KEY", "env-key")
        base = AirBase()
        assert base.api_key == "env-key"

    def test_sets_base_url(self):
        base = AirBase(api_key="k")
        assert base.base_url == "https://data.moenv.gov.tw/api/v2"

    def test_forwards_retry_settings_to_handler(self):
        base = AirBase(api_key="k", max_retries=5, retry_delay=1, backoff_factor=1.5)
        assert base.max_retries == 5
        assert base.retry_delay == 1
        assert base.backoff_factor == 1.5


class TestFetch:
    def _make_response(self, payload, status_ok=True):
        response = MagicMock()
        response.json.return_value = payload
        if status_ok:
            response.raise_for_status.return_value = None
        else:
            response.raise_for_status.side_effect = Exception("HTTP error")
        return response

    def test_builds_url_and_base_params(self, monkeypatch):
        base = AirBase(api_key="k")
        response = self._make_response([])
        mock_get = MagicMock(return_value=response)
        monkeypatch.setattr("domain.air.providers.base.requests.get", mock_get)

        base._fetch("aqx_p_432")

        mock_get.assert_called_once_with(
            "https://data.moenv.gov.tw/api/v2/aqx_p_432",
            params={"api_key": "k", "format": "JSON"},
            timeout=15,
        )

    def test_includes_limit_and_offset_only_when_given(self, monkeypatch):
        base = AirBase(api_key="k")
        response = self._make_response([])
        mock_get = MagicMock(return_value=response)
        monkeypatch.setattr("domain.air.providers.base.requests.get", mock_get)

        base._fetch("aqx_p_432", limit=10, offset=20)

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["limit"] == 10
        assert kwargs["params"]["offset"] == 20

    def test_raises_for_http_error_status(self, monkeypatch):
        base = AirBase(api_key="k")
        response = self._make_response({}, status_ok=False)
        monkeypatch.setattr("domain.air.providers.base.requests.get", MagicMock(return_value=response))

        with pytest.raises(Exception, match="HTTP error"):
            base._fetch("aqx_p_432")

    def test_normalizes_dates_in_response(self, monkeypatch):
        base = AirBase(api_key="k")
        response = self._make_response(
            [{"monitordate": "2024/01/02", "aqi": "50"}]
        )
        monkeypatch.setattr("domain.air.providers.base.requests.get", MagicMock(return_value=response))

        result = base._fetch("aqx_p_432")

        assert result[0]["monitordate"] == "2024-01-02"
        assert result[0]["aqi"] == "50"


class TestNormalizeDates:
    def test_normalizes_keys_matching_date_or_time_hint_case_insensitively(self):
        base = AirBase(api_key="k")
        records = [{"PublishTime": "2024/01/02 03:04:05", "monitordate": "20240103"}]

        result = base._normalize_dates(records)

        assert result[0]["PublishTime"] == "2024-01-02 03:04:05"
        assert result[0]["monitordate"] == "2024-01-03"

    def test_leaves_non_date_keys_untouched(self):
        base = AirBase(api_key="k")
        records = [{"aqi": "50", "county": "Taipei"}]

        result = base._normalize_dates(records)

        assert result == [{"aqi": "50", "county": "Taipei"}]

    def test_keeps_original_value_when_unparseable(self):
        base = AirBase(api_key="k")
        records = [{"monitordate": "not-a-date"}]

        result = base._normalize_dates(records)

        assert result[0]["monitordate"] == "not-a-date"

    def test_mutates_and_returns_same_list(self):
        base = AirBase(api_key="k")
        records = [{"monitordate": "2024/01/02"}]

        result = base._normalize_dates(records)

        assert result is records


class TestGetData:
    def test_delegates_to_fetch_via_retry(self, monkeypatch):
        base = AirBase(api_key="k")
        mock_fetch = MagicMock(return_value={"records": []})
        monkeypatch.setattr(base, "_fetch", mock_fetch)

        result = base._get_data(data_id="aqx_p_432", limit=5, offset=0)

        mock_fetch.assert_called_once_with("aqx_p_432", limit=5, offset=0)
        assert result == {"records": []}

    def test_retries_on_transient_failure(self, monkeypatch):
        base = AirBase(api_key="k", retry_delay=0, backoff_factor=1)
        monkeypatch.setattr("domain.core.base.time.sleep", lambda seconds: None)

        attempts = {"count": 0}

        def flaky_fetch(data_id, limit=None, offset=None):
            attempts["count"] += 1
            if attempts["count"] < 2:
                raise ConnectionError("network blip")
            return {"records": ["ok"]}

        monkeypatch.setattr(base, "_fetch", flaky_fetch)

        result = base._get_data(data_id="aqx_p_432")

        assert result == {"records": ["ok"]}
        assert attempts["count"] == 2
