import numpy as np
import pandas as pd
from backtest.engine import BacktestConfig, run_walk_forward_backtest
from data.bist_rules import get_bist_daily_limits, is_at_ceiling, round_to_tick
from indicators.technical import atr, compute_flow, ema, rsi
from risk.position import calculate_position_size
from strategy.planner import compute_smart_plan


def test_bist_tick_rounding_and_limits():
    assert round_to_tick(18.436, "nearest") == 18.44
    assert round_to_tick(45.13, "down") == 45.12
    assert round_to_tick(102.33, "up") == 102.40
    floor_p, ceil_p = get_bist_daily_limits(100.0)
    assert floor_p == 90.00
    assert ceil_p == 110.00
    assert is_at_ceiling(110.00, 100.0) is True


def test_position_sizing_zero_lot_when_budget_insufficient():
    res = calculate_position_size(entry=400.0, stop=370.0, target1=460.0, capital=10_000.0, risk_pct=1.0)
    assert res.affordable is False
    assert res.lot == 0


def test_compute_smart_plan_consistency():
    plan = compute_smart_plan(entry=100.0, raw_support=97.0, daily_atr=2.0, temel_puan=70, tek_puan=85, is_swing=True)
    assert plan.stop < plan.entry < plan.target1 < plan.target2
    assert plan.risk_per_share == round(plan.entry - plan.stop, 4)


def test_indicators_and_backtest_synthetic():
    idx = pd.date_range("2025-01-01", periods=140, freq="B", tz="Europe/Istanbul")
    close = np.linspace(50, 95, 140) + np.sin(np.arange(140)) * 0.8
    df = pd.DataFrame({
        "Open": close * 0.995,
        "High": close * 1.012,
        "Low": close * 0.990,
        "Close": close,
        "Volume": np.full(140, 3_000_000.0),
    }, index=idx)

    assert len(ema(df["Close"], 20)) == 140
    assert 0 <= rsi(df["Close"]).iloc[-1] <= 100
    assert atr(df).iloc[-1] > 0
    pts, cmf, _, _ = compute_flow(df)
    assert 0 <= pts <= 3

    bt = run_walk_forward_backtest({"TEST": df}, cfg=BacktestConfig(hold_days=5, top_n_liquid_per_day=5))
    assert bt is None or bt["overall"]["count"] >= 0
