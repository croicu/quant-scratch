from __future__ import annotations

from datetime import datetime, timezone

import pytest

from shared.errors import AppError
from shared.sessions import AFTER_MARKET, PRE_MARKET, REGULAR, infer_session


def test_infer_session_pre_market_boundary():
    assert infer_session(datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)) == PRE_MARKET  # 04:00 ET


def test_infer_session_regular_open_boundary():
    assert infer_session(datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)) == REGULAR  # 09:30 ET


def test_infer_session_regular_midday():
    assert infer_session(datetime(2026, 1, 2, 18, 0, tzinfo=timezone.utc)) == REGULAR  # 13:00 ET


def test_infer_session_after_market_open_boundary():
    assert infer_session(datetime(2026, 1, 2, 21, 0, tzinfo=timezone.utc)) == AFTER_MARKET  # 16:00 ET


def test_infer_session_after_market_evening():
    assert infer_session(datetime(2026, 1, 2, 23, 0, tzinfo=timezone.utc)) == AFTER_MARKET  # 18:00 ET


def test_infer_session_raises_outside_known_hours():
    with pytest.raises(AppError):
        infer_session(datetime(2026, 1, 2, 6, 0, tzinfo=timezone.utc))  # 01:00 ET
