from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from config import DEFAULT_BSMV_RATE, DEFAULT_COMMISSION_RATE, DEFAULT_SLIPPAGE_RATE
from indicators.technical import atr, check_wick_health, ema, rsi
from strategy.planner import compute_smart_plan


@dataclass
class BacktestConfig:
    hold_days: int = 5
    top_n_liquid_per_day: int = 40
    min_tl_vol_m: float = 50.0
    commission_rate: float = DEFAULT_COMMISSION_RATE
    bsmv_rate: float = DEFAULT_BSMV_RATE
    slippage_rate: float = DEFAULT_SLIPPAGE_RATE
    use_regime_filter: bool = True
    in_sample_ratio: float = 0.70


def _round_trip_cost_r(entry: float, exit_p: float, risk_unit: float, cfg: BacktestConfig) -> float:
    eff_comm = cfg.commission_rate * (1.0 + cfg.bsmv_rate)
    total_cost_tl = (entry + exit_p) * (eff_comm + cfg.slippage_rate)
    return total_cost_tl / max(risk_unit, 0.01)


def run_walk_forward_backtest(
    daily_dict: Dict[str, pd.DataFrame],
    xu100_df: Optional[pd.DataFrame] = None,
    cfg: Optional[BacktestConfig] = None,
    fund_scores: Optional[Dict[str, Optional[float]]] = None,
) -> Optional[dict]:
    cfg = cfg or BacktestConfig()
    fund_scores = fund_scores or {}

    prepared: Dict[str, pd.DataFrame] = {}
    all_dates = set()
    for t, d in daily_dict.items():
        if d is None or len(d) < 80:
            continue
        df = d.copy()
        df["ema20"] = ema(df["Close"], 20)
        df["ema50"] = ema(df["Close"], 50)
        df["rsi"] = rsi(df["Close"])
        df["atr"] = atr(df)
        df["vol20"] = df["Volume"].rolling(20).mean()
        df["tl_vol"] = (df["Close"] * df["Volume"]).rolling(20).mean() / 1e6
        df["recent_low5"] = df["Low"].rolling(5).min()
        prepared[t] = df
        all_dates.update(df.index[55:])

    if not prepared or not all_dates:
        return None

    sorted_dates = sorted(all_dates)
    regime_ok_by_date: Dict[pd.Timestamp, bool] = {}
    if cfg.use_regime_filter and xu100_df is not None and len(xu100_df) >= 25:
        xdf = xu100_df.copy()
        xdf["ema20"] = ema(xdf["Close"], 20)
        xdf["chg"] = xdf["Close"].pct_change() * 100
        for dt, r in xdf.iterrows():
            regime_ok_by_date[dt] = bool((r["chg"] > -1.2) and (r["Close"] >= r["ema20"] * 0.99))

    open_positions: Dict[str, dict] = {}
    trades: List[dict] = []

    for dt in sorted_dates:
        to_close = []
        for t, pos in open_positions.items():
            df = prepared[t]
            if dt not in df.index:
                continue
            row = df.loc[dt]
            pos["days_held"] += 1

            if float(row["Open"]) <= pos["stop"]:
                fill_p = float(row["Open"])
                raw_r = (fill_p - pos["entry"]) / pos["risk_unit"]
                net_r = raw_r - _round_trip_cost_r(pos["entry"], fill_p, pos["risk_unit"], cfg)
                trades.append({"Tarih": dt, "Hisse": t, "Sonuç": "Gap Stop", "R": net_r})
                to_close.append(t)
            elif float(row["Low"]) <= pos["stop"]:
                fill_p = pos["stop"]
                raw_r = -1.0
                net_r = raw_r - _round_trip_cost_r(pos["entry"], fill_p, pos["risk_unit"], cfg)
                trades.append({"Tarih": dt, "Hisse": t, "Sonuç": "Zarar Kes", "R": net_r})
                to_close.append(t)
            elif float(row["High"]) >= pos["target"]:
                fill_p = pos["target"]
                raw_r = (fill_p - pos["entry"]) / pos["risk_unit"]
                net_r = raw_r - _round_trip_cost_r(pos["entry"], fill_p, pos["risk_unit"], cfg)
                trades.append({"Tarih": dt, "Hisse": t, "Sonuç": "Kâr Hedefi", "R": net_r})
                to_close.append(t)
            elif pos["days_held"] >= cfg.hold_days:
                fill_p = float(row["Close"])
                raw_r = (fill_p - pos["entry"]) / pos["risk_unit"]
                net_r = raw_r - _round_trip_cost_r(pos["entry"], fill_p, pos["risk_unit"], cfg)
                trades.append({"Tarih": dt, "Hisse": t, "Sonuç": "Süre Sonu", "R": net_r})
                to_close.append(t)

        for t in to_close:
            del open_positions[t]

        if cfg.use_regime_filter and regime_ok_by_date and not regime_ok_by_date.get(dt, True):
            continue

        day_candidates = []
        for t, df in prepared.items():
            if t in open_positions or dt not in df.index:
                continue
            row = df.loc[dt]
            if pd.notna(row["tl_vol"]) and row["tl_vol"] >= cfg.min_tl_vol_m:
                day_candidates.append((float(row["tl_vol"]), t, row))

        day_candidates.sort(key=lambda x: x[0], reverse=True)
        for _, t, row in day_candidates[: cfg.top_n_liquid_per_day]:
            wick_ok, _ = check_wick_health(row)
            rvol = float(row["Volume"] / row["vol20"]) if row["vol20"] > 0 else 0.0
            cond = (
                row["Close"] > row["ema20"] > row["ema50"]
                and 50 <= row["rsi"] <= 68
                and rvol >= 1.1
                and wick_ok
                and row["atr"] > 0
            )
            if not cond:
                continue
            entry_p = float(row["Close"])
            raw_sup = max(float(row["ema20"]), float(row["recent_low5"]))
            plan = compute_smart_plan(
                entry=entry_p,
                raw_support=raw_sup,
                daily_atr=float(row["atr"]),
                temel_puan=fund_scores.get(t),
                tek_puan=80.0,
                is_swing=True,
            )
            if 0 < plan.risk_per_share <= 1.8 * float(row["atr"]):
                open_positions[t] = {
                    "entry": plan.entry,
                    "stop": plan.stop,
                    "target": plan.target1,
                    "risk_unit": plan.risk_per_share,
                    "days_held": 0,
                }

    if not trades:
        return None

    tdf = pd.DataFrame(trades).sort_values("Tarih").reset_index(drop=True)
    tdf["Kümülatif Kazanç (R)"] = tdf["R"].cumsum()
    tdf["Peak (R)"] = tdf["Kümülatif Kazanç (R)"].cummax()
    tdf["Drawdown (R)"] = tdf["Kümülatif Kazanç (R)"] - tdf["Peak (R)"]

    split_idx = max(1, int(len(tdf) * cfg.in_sample_ratio))
    is_df = tdf.iloc[:split_idx]
    oos_df = tdf.iloc[split_idx:]

    def _stats(sub: pd.DataFrame) -> dict:
        if sub.empty:
            return {"count": 0, "win_rate": 0.0, "pf": 0.0, "expectancy": 0.0, "net_r": 0.0, "max_dd": 0.0, "sharpe": 0.0, "sortino": 0.0}
        wins = sub[sub["R"] > 0]["R"]
        losses = sub[sub["R"] <= 0]["R"]
        wr = len(wins) / len(sub) * 100.0
        pf = float(wins.sum() / abs(losses.sum())) if losses.sum() < 0 else np.inf
        exp_r = float(sub["R"].mean())
        std_r = float(sub["R"].std(ddof=1)) if len(sub) > 1 else 0.0
        down_std = float(losses.std(ddof=1)) if len(losses) > 1 else 0.0
        sharpe = (exp_r / std_r * np.sqrt(len(sub))) if std_r > 0 else 0.0
        sortino = (exp_r / down_std * np.sqrt(len(sub))) if down_std > 0 else 0.0
        cum = sub["R"].cumsum()
        max_dd = float((cum - cum.cummax()).min())
        return {
            "count": len(sub),
            "win_rate": round(wr, 1),
            "pf": round(pf, 2) if np.isfinite(pf) else 99.0,
            "expectancy": round(exp_r, 3),
            "net_r": round(float(sub["R"].sum()), 2),
            "max_dd": round(max_dd, 2),
            "sharpe": round(sharpe, 2),
            "sortino": round(sortino, 2),
        }

    tdf["Ay"] = pd.to_datetime(tdf["Tarih"]).dt.to_period("M").astype(str)
    monthly = tdf.groupby("Ay", as_index=False)["R"].agg(İşlem="count", Net_R="sum", Ortalama_R="mean")

    return {
        "overall": _stats(tdf),
        "in_sample": _stats(is_df),
        "out_of_sample": _stats(oos_df),
        "monthly": monthly,
        "df": tdf,
    }
