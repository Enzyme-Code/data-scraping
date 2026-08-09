import pytest

from domain.core import Handler


def test_defaults():
    handler = Handler()
    assert handler.debug is False
    assert handler.max_retries == 3
    assert handler.retry_delay == 2
    assert handler.backoff_factor == 2.0


def test_debug_prints_when_enabled(capsys):
    handler = Handler(debug=True)
    handler._debug("hello")
    captured = capsys.readouterr()
    assert "[DEBUG] hello" in captured.out


def test_debug_silent_when_disabled(capsys):
    handler = Handler(debug=False)
    handler._debug("hello")
    captured = capsys.readouterr()
    assert captured.out == ""


def test_retry_succeeds_on_first_attempt():
    handler = Handler()
    calls = []

    def func():
        calls.append(1)
        return "ok"

    assert handler._retry(func) == "ok"
    assert len(calls) == 1


def test_retry_recovers_after_transient_failures(monkeypatch):
    handler = Handler(max_retries=3, retry_delay=1, backoff_factor=2.0)
    sleeps = []
    monkeypatch.setattr("domain.core.base.time.sleep", lambda seconds: sleeps.append(seconds))

    attempts = {"count": 0}

    def func():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ValueError("transient")
        return "recovered"

    assert handler._retry(func) == "recovered"
    assert attempts["count"] == 3
    # Delay backs off geometrically between the two failed attempts.
    assert sleeps == [1, 2]


def test_retry_raises_after_exhausting_max_retries(monkeypatch):
    handler = Handler(max_retries=2, retry_delay=1, backoff_factor=2.0)
    monkeypatch.setattr("domain.core.base.time.sleep", lambda seconds: None)

    attempts = {"count": 0}

    def func():
        attempts["count"] += 1
        raise ValueError("permanent failure")

    with pytest.raises(ValueError, match="permanent failure"):
        handler._retry(func)

    # Initial attempt + max_retries retries.
    assert attempts["count"] == 3


def test_retry_passes_args_and_kwargs_through():
    handler = Handler()

    def func(a, b, c=None):
        return a, b, c

    assert handler._retry(func, 1, 2, c=3) == (1, 2, 3)
