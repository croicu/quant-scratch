from __future__ import annotations

from datetime import date

import pytest
import requests
from requests.exceptions import HTTPError

from shared.errors import AppError
from shared.providers.massive import MassiveIntraDay

_TARGET_DATE = date(2026, 7, 31)


def _http_error(status_code: int) -> HTTPError:
    response = requests.Response()
    response.status_code = status_code
    return HTTPError(f"{status_code} Client Error", response=response)


class _RecordingSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


# Shape confirmed against the real API (live-verified 2026-08-15).
_SAMPLE_PAYLOAD = {
    "ticker": "SPY",
    "queryCount": 2,
    "resultsCount": 2,
    "adjusted": True,
    "results": [
        {"v": 9533.002, "vw": 745.14, "o": 745.6, "c": 745.4, "h": 745.73, "l": 744.07, "t": 1785484860000, "n": 288},
        {"v": 6319.407237, "vw": 745.3721, "o": 745.06, "c": 745.53, "h": 745.84, "l": 744.22, "t": 1785484800000, "n": 454},
    ],
    "status": "OK",
    "request_id": "test-request-id",
    "count": 2,
}


def test_fetch_bars_parses_and_sorts_chronologically():
    provider = MassiveIntraDay(api_key="test-key", request_fn=lambda url, params: _SAMPLE_PAYLOAD)

    bars = provider.fetch_bars("spy", _TARGET_DATE)

    assert len(bars) == 2
    assert bars[0].timestamp < bars[1].timestamp
    assert bars[0].open == 745.06
    assert bars[0].volume == 6319  # truncated from the fractional 6319.407237
    assert bars[1].close == 745.4


def test_fetch_bars_sends_expected_url_and_params():
    captured = {}

    def fake_request(url: str, params: dict) -> dict:
        captured["url"] = url
        captured["params"] = params
        return _SAMPLE_PAYLOAD

    provider = MassiveIntraDay(api_key="test-key", request_fn=fake_request)
    provider.fetch_bars("spy", _TARGET_DATE)

    assert captured["url"] == "https://api.massive.com/v2/aggs/ticker/SPY/range/1/minute/2026-07-31/2026-07-31"
    assert captured["params"] == {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": "test-key"}


def test_fetch_bars_raises_on_error_status():
    payload = {"status": "ERROR", "error": "Unknown API Key"}
    provider = MassiveIntraDay(api_key="bad-key", request_fn=lambda url, params: payload)

    with pytest.raises(AppError, match="Unknown API Key"):
        provider.fetch_bars("spy", _TARGET_DATE)


def test_fetch_bars_raises_when_no_results():
    # Real shape for a weekend/holiday or invalid ticker: status OK, no 'results' key at all.
    payload = {"ticker": "SPY", "queryCount": 0, "resultsCount": 0, "adjusted": True, "status": "OK"}
    provider = MassiveIntraDay(api_key="test-key", request_fn=lambda url, params: payload)

    with pytest.raises(AppError, match="No data available"):
        provider.fetch_bars("spy", _TARGET_DATE)


def test_fetch_bars_wraps_request_exception():
    def failing_request(url: str, params: dict) -> dict:
        raise ConnectionError("network down")

    provider = MassiveIntraDay(api_key="test-key", request_fn=failing_request)

    with pytest.raises(AppError, match="network down"):
        provider.fetch_bars("spy", _TARGET_DATE)


def test_fetch_bars_retries_on_rate_limit_then_succeeds():
    responses = [_http_error(429), _http_error(429), _SAMPLE_PAYLOAD]

    def fake_request(url: str, params: dict) -> dict:
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    sleep = _RecordingSleep()
    provider = MassiveIntraDay(api_key="test-key", request_fn=fake_request, sleep_fn=sleep)

    bars = provider.fetch_bars("spy", _TARGET_DATE)

    assert len(bars) == 2
    assert sleep.calls == [15.0, 15.0]


def test_fetch_bars_raises_after_exhausting_retries_on_persistent_rate_limit():
    def always_rate_limited(url: str, params: dict) -> dict:
        raise _http_error(429)

    sleep = _RecordingSleep()
    provider = MassiveIntraDay(api_key="test-key", request_fn=always_rate_limited, sleep_fn=sleep)

    with pytest.raises(AppError, match="still rate-limited"):
        provider.fetch_bars("spy", _TARGET_DATE)

    # 3 attempts total (default max_attempts), sleeping between each but not after the last.
    assert sleep.calls == [15.0, 15.0]


def test_fetch_bars_does_not_retry_on_non_rate_limit_http_error():
    call_count = {"count": 0}

    def forbidden(url: str, params: dict) -> dict:
        call_count["count"] += 1
        raise _http_error(403)

    sleep = _RecordingSleep()
    provider = MassiveIntraDay(api_key="test-key", request_fn=forbidden, sleep_fn=sleep)

    with pytest.raises(AppError, match="403"):
        provider.fetch_bars("spy", _TARGET_DATE)

    assert call_count["count"] == 1
    assert sleep.calls == []


def test_fetch_bars_respects_custom_max_attempts_and_retry_delay():
    def always_rate_limited(url: str, params: dict) -> dict:
        raise _http_error(429)

    sleep = _RecordingSleep()
    provider = MassiveIntraDay(api_key="test-key", request_fn=always_rate_limited, max_attempts=2, retry_delay_seconds=5.0, sleep_fn=sleep)

    with pytest.raises(AppError, match="after 2 attempts"):
        provider.fetch_bars("spy", _TARGET_DATE)

    assert sleep.calls == [5.0]


def test_fetch_quote_bars_reads_wap_and_trade_count_from_fetch_bars_cache_without_a_second_call():
    call_count = {"count": 0}

    def counting_request(url: str, params: dict) -> dict:
        call_count["count"] += 1
        return _SAMPLE_PAYLOAD

    provider = MassiveIntraDay(api_key="test-key", request_fn=counting_request)
    provider.fetch_bars("spy", _TARGET_DATE)

    quote_bars = provider.fetch_quote_bars("spy", _TARGET_DATE)

    # Free tier is hard rate-limited to 5 calls/minute -- fetch_quote_bars must reuse fetch_bars's
    # own response rather than issuing its own request.
    assert call_count["count"] == 1
    assert len(quote_bars) == 2
    assert quote_bars[0].timestamp < quote_bars[1].timestamp
    assert quote_bars[0].wap == 745.3721
    assert quote_bars[0].trade_count == 454
    assert quote_bars[1].wap == 745.14
    assert quote_bars[1].trade_count == 288


def test_fetch_quote_bars_avg_bid_and_avg_ask_are_always_none():
    # Massive's free Basic tier has no bid/ask/NBBO product at all (confirmed live -- /v3/quotes
    # 403s "not entitled"), unlike IBKR's separate BID_ASK call.
    provider = MassiveIntraDay(api_key="test-key", request_fn=lambda url, params: _SAMPLE_PAYLOAD)
    provider.fetch_bars("spy", _TARGET_DATE)

    quote_bars = provider.fetch_quote_bars("spy", _TARGET_DATE)

    for quote_bar in quote_bars:
        assert quote_bar.avg_bid is None
        assert quote_bar.avg_ask is None


def test_fetch_quote_bars_raises_when_fetch_bars_was_not_called_first():
    provider = MassiveIntraDay(api_key="test-key", request_fn=lambda url, params: _SAMPLE_PAYLOAD)

    with pytest.raises(AppError, match="fetch_bars must be called"):
        provider.fetch_quote_bars("spy", _TARGET_DATE)


def test_fetch_quote_bars_is_scoped_to_its_own_ticker_and_date():
    provider = MassiveIntraDay(api_key="test-key", request_fn=lambda url, params: _SAMPLE_PAYLOAD)
    provider.fetch_bars("spy", _TARGET_DATE)

    with pytest.raises(AppError, match="fetch_bars must be called"):
        provider.fetch_quote_bars("spy", date(2026, 8, 1))
