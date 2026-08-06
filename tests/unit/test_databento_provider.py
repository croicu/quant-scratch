from __future__ import annotations

from datetime import date

import databento as db
import pandas as pd
import pytest

from defs.protocols import DayBar
from shared.errors import AppError
from shared.providers.databento import DEFAULT_DATASET, DatabentoIntraDay


class FakeDBNStore:
    def __init__(self, frame: pd.DataFrame):
        self._frame = frame

    def to_df(self, price_type=None, tz=None):
        return self._frame


class FakeTimeSeries:
    def __init__(self, frame: pd.DataFrame | None = None, error: Exception | None = None, responses: list | None = None):
        # `responses`, if given, is a list of per-call outcomes (a DataFrame to succeed with, or
        # an Exception to raise) consumed one per get_range() call -- lets a test script a
        # fail-then-succeed (or fail-N-times) sequence. `frame`/`error` remain as the simpler
        # single-outcome-every-call shape the non-retry tests already use.
        self._responses = None if responses is None else list(responses)
        self._frame = frame if frame is not None else pd.DataFrame()
        self._error = error
        self.get_range_kwargs: dict | None = None
        self.call_count = 0

    def get_range(self, **kwargs):
        self.call_count += 1
        self.get_range_kwargs = kwargs
        if self._responses is not None:
            response = self._responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return FakeDBNStore(response)
        if self._error is not None:
            raise self._error
        return FakeDBNStore(self._frame)


class FakeHistorical:
    def __init__(self, frame: pd.DataFrame | None = None, error: Exception | None = None, responses: list | None = None):
        self.timeseries = FakeTimeSeries(frame=frame, error=error, responses=responses)
        self.api_key: str | None = None

    def __call__(self, api_key: str):
        self.api_key = api_key
        return self


class RecordingSleep:
    def __init__(self):
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _sample_frame() -> pd.DataFrame:
    index = pd.to_datetime(
        ["2026-07-31T09:00:00Z", "2026-07-31T14:30:00Z"],  # 05:00 ET pre-market, 10:30 ET regular
    ).tz_convert("UTC")
    return pd.DataFrame(
        {
            "open": [470.0, 471.5],
            "high": [470.5, 472.4],
            "low": [469.8, 471.3],
            "close": [470.2, 472.1],
            "volume": [0, 250000],
        },
        index=index,
    )


def test_fetch_bars_converts_dataframe_rows_to_daybar_with_session():
    fake_historical = FakeHistorical(frame=_sample_frame())
    provider = DatabentoIntraDay(api_key="db-test-key", client_factory=fake_historical)

    bars = provider.fetch_bars("spy", date(2026, 7, 31))

    assert len(bars) == 2
    assert isinstance(bars[0], DayBar)
    assert bars[0].session == "pre-market"
    assert bars[0].volume == 0
    assert bars[1].session == "regular"
    assert bars[1].volume == 250000
    assert bars[1].close == 472.1


def test_fetch_bars_requests_ohlcv_1m_for_the_given_dataset_and_symbol():
    fake_historical = FakeHistorical(frame=_sample_frame())
    provider = DatabentoIntraDay(api_key="db-test-key", dataset="XNAS.ITCH", client_factory=fake_historical)

    provider.fetch_bars("SPY", date(2026, 7, 31))

    kwargs = fake_historical.timeseries.get_range_kwargs
    assert kwargs["dataset"] == "XNAS.ITCH"
    assert kwargs["symbols"] == ["SPY"]
    assert kwargs["schema"].value == "ohlcv-1m"


def test_fetch_bars_uses_default_dataset_when_not_overridden():
    fake_historical = FakeHistorical(frame=_sample_frame())
    provider = DatabentoIntraDay(api_key="db-test-key", client_factory=fake_historical)

    provider.fetch_bars("SPY", date(2026, 7, 31))

    assert fake_historical.timeseries.get_range_kwargs["dataset"] == DEFAULT_DATASET


def test_fetch_bars_passes_api_key_to_client_factory():
    fake_historical = FakeHistorical(frame=_sample_frame())
    provider = DatabentoIntraDay(api_key="db-test-key", client_factory=fake_historical)

    provider.fetch_bars("SPY", date(2026, 7, 31))

    assert fake_historical.api_key == "db-test-key"


def test_fetch_bars_raises_on_empty_result():
    fake_historical = FakeHistorical(frame=pd.DataFrame())
    provider = DatabentoIntraDay(api_key="db-test-key", client_factory=fake_historical)

    with pytest.raises(AppError):
        provider.fetch_bars("SPY", date(2026, 7, 31))


def test_fetch_bars_raises_on_request_error():
    fake_historical = FakeHistorical(error=RuntimeError("no entitlement"))
    provider = DatabentoIntraDay(api_key="db-test-key", client_factory=fake_historical)

    with pytest.raises(AppError):
        provider.fetch_bars("SPY", date(2026, 7, 31))


def test_fetch_bars_retries_after_server_error_then_succeeds():
    # Reproduces the live behavior observed against Databento's gateway: an intermittent 504 on
    # one call, then a clean response on the next, same ticker/date/dataset.
    server_error = db.BentoServerError(http_status=504, message="The remote gateway timed out.")
    fake_historical = FakeHistorical(responses=[server_error, _sample_frame()])
    recording_sleep = RecordingSleep()
    provider = DatabentoIntraDay(api_key="db-test-key", client_factory=fake_historical, sleep_fn=recording_sleep)

    bars = provider.fetch_bars("SPY", date(2026, 7, 31))

    assert len(bars) == 2
    assert fake_historical.timeseries.call_count == 2
    assert recording_sleep.calls == [2.0]


def test_fetch_bars_raises_after_exhausting_retries_on_persistent_server_error():
    server_error = db.BentoServerError(http_status=504, message="The remote gateway timed out.")
    fake_historical = FakeHistorical(responses=[server_error, server_error, server_error])
    recording_sleep = RecordingSleep()
    provider = DatabentoIntraDay(api_key="db-test-key", client_factory=fake_historical, sleep_fn=recording_sleep)

    with pytest.raises(AppError):
        provider.fetch_bars("SPY", date(2026, 7, 31))

    assert fake_historical.timeseries.call_count == 3
    assert recording_sleep.calls == [2.0, 2.0]


def test_fetch_bars_does_not_retry_on_client_error():
    # A 400-series error (bad API key, invalid symbol, etc.) will never succeed on retry --
    # should fail immediately via the same generic-error path as any other non-server exception.
    client_error = db.BentoClientError(http_status=401, message="invalid API key")
    fake_historical = FakeHistorical(responses=[client_error])
    recording_sleep = RecordingSleep()
    provider = DatabentoIntraDay(api_key="db-test-key", client_factory=fake_historical, sleep_fn=recording_sleep)

    with pytest.raises(AppError):
        provider.fetch_bars("SPY", date(2026, 7, 31))

    assert fake_historical.timeseries.call_count == 1
    assert recording_sleep.calls == []


def test_fetch_bars_respects_custom_max_attempts_and_retry_delay():
    server_error = db.BentoServerError(http_status=504, message="The remote gateway timed out.")
    fake_historical = FakeHistorical(responses=[server_error, server_error])
    recording_sleep = RecordingSleep()
    provider = DatabentoIntraDay(
        api_key="db-test-key",
        client_factory=fake_historical,
        max_attempts=2,
        retry_delay_seconds=5.0,
        sleep_fn=recording_sleep,
    )

    with pytest.raises(AppError):
        provider.fetch_bars("SPY", date(2026, 7, 31))

    assert fake_historical.timeseries.call_count == 2
    assert recording_sleep.calls == [5.0]
