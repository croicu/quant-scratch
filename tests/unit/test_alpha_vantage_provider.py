from __future__ import annotations

from datetime import date

import pytest

from shared.errors import AppError
from shared.providers.alpha_vantage import AlphaVantageIntraDay

_TARGET_DATE = date(2026, 7, 23)

_SAMPLE_PAYLOAD = {
    "Meta Data": {"1. Information": "Intraday (1min) open, high, low, close prices and volume"},
    "Time Series (1min)": {
        "2026-07-23 09:45:00": {
            "1. open": "740.10",
            "2. high": "740.50",
            "3. low": "739.90",
            "4. close": "740.20",
            "5. volume": "12345",
        },
        "2026-07-23 09:30:00": {
            "1. open": "739.00",
            "2. high": "740.00",
            "3. low": "738.90",
            "4. close": "740.10",
            "5. volume": "54321",
        },
        # A different day in the same month -- must be filtered out, not returned alongside
        # target_date's bars.
        "2026-07-22 09:30:00": {
            "1. open": "999.00",
            "2. high": "999.00",
            "3. low": "999.00",
            "4. close": "999.00",
            "5. volume": "1",
        },
    },
}


def test_fetch_bars_parses_sorts_and_filters_to_target_date():
    provider = AlphaVantageIntraDay(api_key="test-key", request_fn=lambda params: _SAMPLE_PAYLOAD)

    bars = provider.fetch_bars("spy", _TARGET_DATE)

    assert len(bars) == 2
    assert bars[0].timestamp < bars[1].timestamp
    assert bars[0].open == 739.00
    assert bars[0].volume == 54321
    assert bars[1].close == 740.20


def test_fetch_bars_sends_expected_params():
    captured = {}

    def fake_request(params: dict) -> dict:
        captured.update(params)
        return _SAMPLE_PAYLOAD

    provider = AlphaVantageIntraDay(api_key="test-key", request_fn=fake_request)
    provider.fetch_bars("spy", _TARGET_DATE)

    assert captured == {
        "function": "TIME_SERIES_INTRADAY",
        "symbol": "SPY",
        "interval": "1min",
        "extended_hours": "true",
        "outputsize": "full",
        "adjusted": "false",
        "month": "2026-07",
        "apikey": "test-key",
    }


def test_fetch_bars_raises_when_no_bars_match_target_date():
    payload = {"Time Series (1min)": {"2026-07-22 09:30:00": _SAMPLE_PAYLOAD["Time Series (1min)"]["2026-07-22 09:30:00"]}}
    provider = AlphaVantageIntraDay(api_key="test-key", request_fn=lambda params: payload)

    with pytest.raises(AppError, match="No data available"):
        provider.fetch_bars("spy", _TARGET_DATE)


def test_fetch_bars_raises_on_error_message():
    payload = {"Error Message": "Invalid API call"}
    provider = AlphaVantageIntraDay(api_key="test-key", request_fn=lambda params: payload)

    with pytest.raises(AppError, match="Invalid API call"):
        provider.fetch_bars("spy", _TARGET_DATE)


def test_fetch_bars_raises_on_rate_limit_note():
    payload = {"Note": "Thank you for using Alpha Vantage! ... call frequency"}
    provider = AlphaVantageIntraDay(api_key="test-key", request_fn=lambda params: payload)

    with pytest.raises(AppError, match="call frequency"):
        provider.fetch_bars("spy", _TARGET_DATE)


def test_fetch_bars_raises_on_unexpected_shape():
    payload = {"Meta Data": {}}
    provider = AlphaVantageIntraDay(api_key="test-key", request_fn=lambda params: payload)

    with pytest.raises(AppError, match="Unexpected Alpha Vantage response shape"):
        provider.fetch_bars("spy", _TARGET_DATE)


def test_fetch_bars_wraps_request_exception():
    def failing_request(params: dict) -> dict:
        raise ConnectionError("network down")

    provider = AlphaVantageIntraDay(api_key="test-key", request_fn=failing_request)

    with pytest.raises(AppError, match="network down"):
        provider.fetch_bars("spy", _TARGET_DATE)
