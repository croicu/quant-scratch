from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from quant_data import OHLCV, DataQuality, PendingResolutionBar, ProviderRole, RejectedWhistleblowerBar

from defs.protocols import BarConflict, DayBar, ProviderBar
from shared.diagnostics import Logger
from shared.errors import AppError
from shared.providers import quant_data as quant_data_module
from shared.providers.quant_data import QuantDataIntraDay


class FakeMarketData:
    def __init__(
        self,
        bars: list[OHLCV] | None = None,
        pending_bars: list[PendingResolutionBar] | None = None,
        rejected_bars: list[RejectedWhistleblowerBar] | None = None,
        error: Exception | None = None,
    ):
        self._bars = bars if bars is not None else []
        self._pending_bars = pending_bars if pending_bars is not None else []
        self._rejected_bars = rejected_bars if rejected_bars is not None else []
        self._error = error
        self.requested: tuple[str, date, date] | None = None
        self.pending_requested: tuple[str, date, date] | None = None
        self.rejected_requested: tuple[str, date, date] | None = None

    def fetch_bars(self, ticker: str, start_date: date, end_date: date) -> list[OHLCV]:
        self.requested = (ticker, start_date, end_date)
        if self._error is not None:
            raise self._error
        return self._bars

    def fetch_pending_resolution_bars(self, ticker: str, start_date: date, end_date: date) -> list[PendingResolutionBar]:
        self.pending_requested = (ticker, start_date, end_date)
        if self._error is not None:
            raise self._error
        return self._pending_bars

    def fetch_rejected_whistleblower_bars(self, ticker: str, start_date: date, end_date: date) -> list[RejectedWhistleblowerBar]:
        self.rejected_requested = (ticker, start_date, end_date)
        if self._error is not None:
            raise self._error
        return self._rejected_bars


def _ohlcv(hour_utc: int, minute_utc: int, close: float, data_quality: DataQuality = DataQuality.ACCEPTED) -> OHLCV:
    return OHLCV(
        ticker="SPY",
        timestamp=datetime(2026, 1, 2, hour_utc, minute_utc, tzinfo=timezone.utc),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000,
        data_quality=data_quality,
    )


def test_fetch_bars_converts_ohlcv_to_daybar_with_session_and_incomplete():
    fake_client = FakeMarketData(
        bars=[
            OHLCV(
                ticker="SPY",
                timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
                open=471.5,
                high=472.4,
                low=471.3,
                close=472.1,
                volume=250000,
                data_quality=DataQuality.ACCEPTED,
            ),
            OHLCV(
                ticker="SPY",
                timestamp=datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc),
                open=470.0,
                high=470.5,
                low=469.8,
                close=470.2,
                volume=0,
                data_quality=DataQuality.INCOMPLETE,
            ),
        ]
    )
    provider = QuantDataIntraDay(client=fake_client)

    bars = provider.fetch_bars("spy", date(2026, 1, 2))

    assert fake_client.requested == ("SPY", date(2026, 1, 2), date(2026, 1, 2))
    assert len(bars) == 2
    assert isinstance(bars[0], DayBar)
    assert bars[0].session == "regular"
    assert bars[0].incomplete is False
    assert bars[1].session == "pre-market"
    assert bars[1].incomplete is True


def test_fetch_bars_treats_rejected_data_quality_as_incomplete():
    # DataQuality.REJECTED collapses into the same DayBar.incomplete=True bucket as INCOMPLETE --
    # the rejected-vs-incomplete distinction lives separately in fetch_rejected_bars, not here.
    fake_client = FakeMarketData(
        bars=[
            OHLCV(
                ticker="SPY",
                timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
                open=471.5,
                high=472.4,
                low=471.3,
                close=472.1,
                volume=250000,
                data_quality=DataQuality.REJECTED,
            ),
        ]
    )
    provider = QuantDataIntraDay(client=fake_client)

    bars = provider.fetch_bars("SPY", date(2026, 1, 2))

    assert bars[0].incomplete is True


def test_fetch_bars_treats_naive_timestamp_as_utc():
    # quant-data's MarketData has been observed returning naive datetimes despite OHLCV.timestamp
    # being documented as timezone-aware UTC (see github.com/croicu/quant-data/issues/8) -- a naive
    # value must be treated as UTC (not silently reinterpreted as the system's local timezone by
    # .astimezone()), or session classification breaks depending on which machine this runs on.
    fake_client = FakeMarketData(
        bars=[
            OHLCV(
                ticker="SPY",
                timestamp=datetime(2026, 1, 2, 14, 30),  # naive, no tzinfo
                open=471.5,
                high=472.4,
                low=471.3,
                close=472.1,
                volume=250000,
                data_quality=DataQuality.ACCEPTED,
            ),
        ]
    )
    provider = QuantDataIntraDay(client=fake_client)

    bars = provider.fetch_bars("SPY", date(2026, 1, 2))

    assert bars[0].timestamp.tzinfo is not None
    assert bars[0].timestamp == datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)
    assert bars[0].session == "regular"


def test_fetch_bars_raises_on_bar_outside_known_session_hours():
    # quant-data#9 (timestamps silently shifted by the write-side session timezone) is fixed and
    # backfilled -- a bar outside the 4:00-20:00 ET window is no longer expected/tolerated, so this
    # should propagate as a hard failure rather than being silently skipped.
    fake_client = FakeMarketData(
        bars=[
            OHLCV(
                ticker="SPY",
                timestamp=datetime(2026, 1, 2, 6, 30, tzinfo=timezone.utc),  # 01:30 ET -- no session
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=858048,
                data_quality=DataQuality.ACCEPTED,
            ),
            OHLCV(
                ticker="SPY",
                timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),  # 09:30 ET -- regular
                open=471.5,
                high=472.4,
                low=471.3,
                close=472.1,
                volume=250000,
                data_quality=DataQuality.ACCEPTED,
            ),
        ]
    )
    provider = QuantDataIntraDay(client=fake_client)

    with pytest.raises(AppError):
        provider.fetch_bars("SPY", date(2026, 1, 2))


def test_fetch_bars_raises_on_empty_result():
    provider = QuantDataIntraDay(client=FakeMarketData(bars=[]))

    with pytest.raises(AppError):
        provider.fetch_bars("SPY", date(2026, 1, 2))


def test_fetch_bars_raises_on_client_error():
    provider = QuantDataIntraDay(client=FakeMarketData(error=RuntimeError("connection reset")))

    with pytest.raises(AppError):
        provider.fetch_bars("SPY", date(2026, 1, 2))


def test_constructor_requires_client_or_connection_details():
    with pytest.raises(AppError):
        QuantDataIntraDay()


def test_constructor_forwards_ssh_kwargs_and_logger_to_create_postgres_provider(monkeypatch):
    captured_kwargs = {}
    captured_market_data_logger = {}

    def fake_create_postgres_provider(**kwargs):
        captured_kwargs.update(kwargs)
        return object()

    def fake_market_data(provider, logger=None):
        captured_market_data_logger["logger"] = logger
        return FakeMarketData()

    monkeypatch.setattr(quant_data_module, "create_postgres_provider", fake_create_postgres_provider)
    monkeypatch.setattr(quant_data_module, "MarketData", fake_market_data)

    QuantDataIntraDay(
        host="CroicuWS1",
        port=5432,
        dbname="quant_data",
        ssh_user="alex",
        ssh_key_path="/home/alex/.ssh/id_ed25519",
    )

    assert captured_kwargs["ssh_user"] == "alex"
    assert captured_kwargs["ssh_key_path"] == "/home/alex/.ssh/id_ed25519"
    # quant-data's LoggingSink protocol expects our own Logger injected (quant-data#20), so its
    # internal timing/connection markers land in the same stream as ours instead of being invisible.
    assert captured_kwargs["logger"] is Logger
    assert captured_market_data_logger["logger"] is Logger


def test_fetch_conflicts_groups_one_whistleblower_and_one_candidate():
    pending_bars = [
        PendingResolutionBar(field_group="ohlc", provider="yfinance", role=ProviderRole.WHISTLEBLOWER, bar=_ohlcv(14, 30, 100.0)),
        PendingResolutionBar(field_group="ohlc", provider="ibkr", role=ProviderRole.CANDIDATE, bar=_ohlcv(14, 30, 100.5)),
    ]
    provider = QuantDataIntraDay(client=FakeMarketData(pending_bars=pending_bars))

    conflicts = provider.fetch_conflicts("spy", date(2026, 1, 2), date(2026, 1, 2))

    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert isinstance(conflict, BarConflict)
    assert conflict.field_group == "ohlc"
    assert conflict.whistleblower.provider == "yfinance"
    assert conflict.whistleblower.bar.close == 100.0
    assert isinstance(conflict.whistleblower.bar, DayBar)
    assert len(conflict.candidates) == 1
    assert conflict.candidates[0].provider == "ibkr"
    assert conflict.candidates[0].bar.close == 100.5


def test_fetch_conflicts_groups_multiple_candidates_under_one_whistleblower():
    pending_bars = [
        PendingResolutionBar(field_group="ohlc", provider="yfinance", role=ProviderRole.WHISTLEBLOWER, bar=_ohlcv(14, 30, 100.0)),
        PendingResolutionBar(field_group="ohlc", provider="ibkr", role=ProviderRole.CANDIDATE, bar=_ohlcv(14, 30, 100.5)),
        PendingResolutionBar(field_group="ohlc", provider="databento", role=ProviderRole.CANDIDATE, bar=_ohlcv(14, 30, 100.7)),
    ]
    provider = QuantDataIntraDay(client=FakeMarketData(pending_bars=pending_bars))

    conflicts = provider.fetch_conflicts("SPY", date(2026, 1, 2), date(2026, 1, 2))

    assert len(conflicts) == 1
    candidate_providers = []
    for candidate in conflicts[0].candidates:
        candidate_providers.append(candidate.provider)
    assert sorted(candidate_providers) == ["databento", "ibkr"]


def test_fetch_conflicts_separates_distinct_timestamps_and_field_groups():
    pending_bars = [
        PendingResolutionBar(field_group="ohlc", provider="yfinance", role=ProviderRole.WHISTLEBLOWER, bar=_ohlcv(14, 30, 100.0)),
        PendingResolutionBar(field_group="ohlc", provider="ibkr", role=ProviderRole.CANDIDATE, bar=_ohlcv(14, 30, 100.5)),
        PendingResolutionBar(field_group="ohlc", provider="yfinance", role=ProviderRole.WHISTLEBLOWER, bar=_ohlcv(14, 31, 101.0)),
        PendingResolutionBar(field_group="ohlc", provider="ibkr", role=ProviderRole.CANDIDATE, bar=_ohlcv(14, 31, 101.5)),
    ]
    provider = QuantDataIntraDay(client=FakeMarketData(pending_bars=pending_bars))

    conflicts = provider.fetch_conflicts("SPY", date(2026, 1, 2), date(2026, 1, 2))

    assert len(conflicts) == 2


def test_fetch_conflicts_raises_on_missing_whistleblower():
    pending_bars = [
        PendingResolutionBar(field_group="ohlc", provider="ibkr", role=ProviderRole.CANDIDATE, bar=_ohlcv(14, 30, 100.5)),
    ]
    provider = QuantDataIntraDay(client=FakeMarketData(pending_bars=pending_bars))

    with pytest.raises(AppError):
        provider.fetch_conflicts("SPY", date(2026, 1, 2), date(2026, 1, 2))


def test_fetch_conflicts_raises_on_multiple_whistleblowers():
    pending_bars = [
        PendingResolutionBar(field_group="ohlc", provider="yfinance", role=ProviderRole.WHISTLEBLOWER, bar=_ohlcv(14, 30, 100.0)),
        PendingResolutionBar(field_group="ohlc", provider="polygon", role=ProviderRole.WHISTLEBLOWER, bar=_ohlcv(14, 30, 100.2)),
        PendingResolutionBar(field_group="ohlc", provider="ibkr", role=ProviderRole.CANDIDATE, bar=_ohlcv(14, 30, 100.5)),
    ]
    provider = QuantDataIntraDay(client=FakeMarketData(pending_bars=pending_bars))

    with pytest.raises(AppError):
        provider.fetch_conflicts("SPY", date(2026, 1, 2), date(2026, 1, 2))


def test_fetch_conflicts_raises_on_missing_candidates():
    pending_bars = [
        PendingResolutionBar(field_group="ohlc", provider="yfinance", role=ProviderRole.WHISTLEBLOWER, bar=_ohlcv(14, 30, 100.0)),
    ]
    provider = QuantDataIntraDay(client=FakeMarketData(pending_bars=pending_bars))

    with pytest.raises(AppError):
        provider.fetch_conflicts("SPY", date(2026, 1, 2), date(2026, 1, 2))


def test_fetch_conflicts_returns_empty_list_when_nothing_pending():
    provider = QuantDataIntraDay(client=FakeMarketData(pending_bars=[]))

    conflicts = provider.fetch_conflicts("SPY", date(2026, 1, 2), date(2026, 1, 2))

    assert conflicts == []


def test_fetch_conflicts_raises_on_client_error():
    provider = QuantDataIntraDay(client=FakeMarketData(error=RuntimeError("connection reset")))

    with pytest.raises(AppError):
        provider.fetch_conflicts("SPY", date(2026, 1, 2), date(2026, 1, 2))


def test_fetch_conflicts_requests_the_full_range():
    fake_client = FakeMarketData(pending_bars=[])

    QuantDataIntraDay(client=fake_client).fetch_conflicts("spy", date(2026, 1, 2), date(2026, 1, 5))

    assert fake_client.pending_requested == ("SPY", date(2026, 1, 2), date(2026, 1, 5))


def test_fetch_rejected_bars_converts_entries_to_provider_bars():
    # No real data exercises data_quality=REJECTED yet (quant-scratch#16 -- deferred until
    # quant-data's own outlier-detection check ships), so this only proves the wiring/conversion
    # is correct against a mocked client, not real rejected data end-to-end.
    rejected_bars = [
        RejectedWhistleblowerBar(provider="yfinance", bar=_ohlcv(14, 30, 100.0, data_quality=DataQuality.REJECTED)),
    ]
    provider = QuantDataIntraDay(client=FakeMarketData(rejected_bars=rejected_bars))

    result = provider.fetch_rejected_bars("spy", date(2026, 1, 2), date(2026, 1, 2))

    assert len(result) == 1
    assert isinstance(result[0], ProviderBar)
    assert result[0].provider == "yfinance"
    assert isinstance(result[0].bar, DayBar)
    assert result[0].bar.close == 100.0


def test_fetch_rejected_bars_returns_empty_list_when_none_rejected():
    provider = QuantDataIntraDay(client=FakeMarketData(rejected_bars=[]))

    result = provider.fetch_rejected_bars("SPY", date(2026, 1, 2), date(2026, 1, 2))

    assert result == []


def test_fetch_rejected_bars_raises_on_client_error():
    provider = QuantDataIntraDay(client=FakeMarketData(error=RuntimeError("connection reset")))

    with pytest.raises(AppError):
        provider.fetch_rejected_bars("SPY", date(2026, 1, 2), date(2026, 1, 2))


def test_fetch_rejected_bars_requests_the_full_range():
    fake_client = FakeMarketData(rejected_bars=[])

    QuantDataIntraDay(client=fake_client).fetch_rejected_bars("spy", date(2026, 1, 2), date(2026, 1, 5))

    assert fake_client.rejected_requested == ("SPY", date(2026, 1, 2), date(2026, 1, 5))
