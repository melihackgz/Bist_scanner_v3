from __future__ import annotations
from typing import Dict, Optional, Set, Tuple
import numpy as np
import pandas as pd
import streamlit as st
from config import INTRADAY_WEIGHTS, SCORE_LABELS, SWING_WEIGHTS, TZ
from data.bist_rules import is_at_ceiling
from data.corporate_actions import detect_unadjusted_split_anomaly
from indicators.technical import (
    atr, check_wick_health, compute_flow, ema,
    get_completed_daily_bars, intraday_elapsed_fraction, is_session_in_progress, rsi
)
from risk.position import calculate_position_size
from strategy.planner import compute_smart_plan


def get_calibrated_label(score: float) -> Tuple[str, str]:
    for threshold, label, col in SCORE_LABELS:
        if score >= threshold:
            return label, col
    return "İZLEME / TEMKİNLİ", "#d97706"


@st.cache_data(ttl=900, show_spinner=False)
def build_daily_summary_table(
    daily: Dict[str, pd.DataFrame],
    min_tl_m: float,
    min_atr: float,
    banned_set: Set[str],
) -> pd.DataFrame:
    rows = []
    now = pd.Timestamp.now(TZ)
    for t, d in daily.items():
        if t in banned_set:
            continue
        d_prev = get_completed_daily_bars(d, now)
        if len(d_prev) < 30:
            continue
        c = float(d_prev["Close"].iloc[-1])
        vol = float((d_prev["Close"] * d_prev["Volume"]).tail(20).mean() / 1e6)
        daily_atr_val = float(atr(d_prev).iloc[-1])
        a_pct = daily_atr_val / c * 100
        ema20 = float(ema(d_prev["Close"], 20).iloc[-1])
        up = c > ema20
        fp, cmf, acc, dist = compute_flow(d_prev, now)
        split_warn, split_msg = detect_unadjusted_split_anomaly(d_prev)
        rows.append({
            "Hisse": t,
            "Kapanış": c,
            "İşlem (M TL)": vol,
            "Hareket %": a_pct,
            "DailyATR": daily_atr_val,
            "ParaP": fp,
            "CMF": cmf,
            "Alım günü": acc,
            "Satım günü": dist,
            "SplitWarn": split_warn,
            "SplitMsg": split_msg,
            "Geçti": bool(vol >= min_tl_m and a_pct >= min_atr and up and c >= 5 and not split_warn),
        })
    return pd.DataFrame(rows)


def apply_live_price(df: pd.DataFrame, live_price: Optional[float]) -> pd.DataFrame:
    if df is None or df.empty or live_price is None or live_price <= 0:
        return df
    out = df.copy()
    idx = out.index[-1]
    out.loc[idx, "Close"] = float(live_price)
    if live_price > float(out.loc[idx, "High"]):
        out.loc[idx, "High"] = float(live_price)
    if live_price < float(out.loc[idx, "Low"]):
        out.loc[idx, "Low"] = float(live_price)
    return out


def analyze_stock_intraday(
    t: str,
    d15: pd.DataFrame,
    d1d: pd.DataFrame,
    params: dict,
    daily_atr: float,
    live_price: Optional[float] = None,
    price_source: str = "Piyasa Verisi",
    updated_at: Optional[str] = None,
) -> Optional[dict]:
    is_live = live_price is not None and live_price > 0
    d = apply_live_price(d15, live_price) if is_live else d15.copy()
    d["day"] = d.index.date
    last_day = d["day"].iloc[-1]
    tp = (d["High"] + d["Low"] + d["Close"]) / 3
    d["vwap"] = (tp * d["Volume"]).groupby(d["day"]).cumsum() / d.groupby("day")["Volume"].cumsum()
    d["cumv"] = d.groupby("day")["Volume"].cumsum()
    d["ema9"], d["ema20"] = ema(d["Close"], 9), ema(d["Close"], 20)
    d["rsi"] = rsi(d["Close"])

    today, prev = d[d["day"] == last_day], d[d["day"] < last_day]
    if prev.empty or today.empty:
        return None

    n = len(today)
    pc = [g["cumv"].iloc[n - 1] for _, g in prev.groupby("day") if len(g) >= n]
    rvol = float(today["cumv"].iloc[-1] / np.mean(pc)) if pc and np.mean(pc) > 0 else np.nan
    prev_close = float(prev["Close"].iloc[-1])
    entry = float(d["Close"].iloc[-1])
    chg = (entry / prev_close - 1) * 100
    r = d.iloc[-1]
    wick_ok, _ = check_wick_health(r)
    ceiling_blocked = is_at_ceiling(entry, prev_close)

    checks = [
        (f"Fiyat gün içi VWAP ({r['vwap']:.2f} TL) üzerinde", bool(r["Close"] > r["vwap"])),
        ("Kısa vadeli trend yukarı (EMA9 > EMA20)", bool(r["ema9"] > r["ema20"] and r["Close"] > r["ema20"])),
        (f"Günlük değişim hedef bantta (%{chg:+.1f})", bool(params["chg_lo"] <= chg <= params["chg_hi"])),
        (f"Momentum dengeli (RSI {r['rsi']:.0f})", bool(params["rsi_lo"] <= r["rsi"] <= params["rsi_hi"])),
        (f"Göreceli hacim yeterli (RVOL {rvol:.2f}x)", bool(rvol >= params["rvol"])),
        ("Üst fitil satış baskısı sınırlı", wick_ok),
        ("Hisse tavan fiyatta değil (Alım yapılabilir)", not ceiling_blocked),
    ]

    raw_support = max(min(float(r["vwap"]), float(r["ema20"])), float(today["Low"].min()))
    puan = sum(ok for _, ok in checks)
    toplam = len(checks)
    tek = puan / toplam * 100

    plan = compute_smart_plan(entry, raw_support, daily_atr, None, tek, is_swing=False, prev_close=prev_close)
    pos = calculate_position_size(
        plan.entry, plan.stop, plan.target1, params["capital"], params["risk_pct"],
        commission_rate=params["comm"], bsmv_rate=params["bsmv"], slippage_rate=params["slip"],
    )
    fp, _, _, _ = compute_flow(d1d)
    para_score = fp / 3 * 100
    genel = INTRADAY_WEIGHTS["tek"] * tek + INTRADAY_WEIGHTS["para"] * para_score

    return {
        "Hisse": t, "Fiyat": plan.entry, "Değişim": chg, "Kontroller": checks,
        "Puan": puan, "Toplam": toplam, "Tek": tek, "Para": para_score, "Temel": None, "Genel": genel,
        "Stop": plan.stop, "Risk": plan.risk_per_share, "Hedef1": plan.target1, "Hedef2": plan.target2,
        "Pos": pos, "IsWide": plan.is_wide, "PlanNote": plan.plan_note, "BandClamped": plan.band_clamped,
        "IsLive": is_live, "PriceSource": price_source, "UpdatedAt": updated_at or d.index[-1].strftime("%d.%m %H:%M"),
        "RVOL": rvol,
    }


def analyze_stock_swing(
    t: str,
    d1d: pd.DataFrame,
    params: dict,
    daily_atr: float,
    temel_puan: Optional[int] = None,
    live_price: Optional[float] = None,
    price_source: str = "Piyasa Verisi",
    updated_at: Optional[str] = None,
) -> Optional[dict]:
    if len(d1d) < 55:
        return None
    now = pd.Timestamp.now(TZ)
    is_live = live_price is not None and live_price > 0
    d = apply_live_price(d1d, live_price) if is_live else d1d.copy()

    d["ema20"] = ema(d["Close"], 20)
    d["ema50"] = ema(d["Close"], 50)
    d["rsi"] = rsi(d["Close"])
    d["vol20"] = d["Volume"].rolling(20).mean()

    r = d.iloc[-1]
    prev = d.iloc[-2]
    prev_close = float(prev["Close"])
    entry = float(r["Close"])
    chg = (entry / prev_close - 1) * 100

    raw_rvol = float(r["Volume"] / r["vol20"]) if r["vol20"] > 0 else 1.0
    if is_session_in_progress(now) and d.index[-1].date() == now.date():
        rvol = raw_rvol / intraday_elapsed_fraction(now)
        wick_row = prev
    else:
        rvol = raw_rvol
        wick_row = r

    wick_ok, _ = check_wick_health(wick_row)
    ceiling_blocked = is_at_ceiling(entry, prev_close)

    checks = [
        ("Orta/uzun vade trend yukarı (Fiyat > EMA20 > EMA50)", bool(r["Close"] > r["ema20"] > r["ema50"])),
        (f"Momentum dengeli (RSI {r['rsi']:.0f})", bool(50 <= r["rsi"] <= 68)),
        (f"Normalize alıcı hacmi ortalamanın üzerinde ({rvol:.2f}x)", bool(rvol >= 1.1)),
        (f"Fiyat aşırı primli değil (%{chg:+.1f})", bool(-1.0 <= chg <= 6.5)),
        ("Tamamlanmış mumda üst fitil baskısı yok", wick_ok),
        ("Hisse tavan fiyatta değil (Alım yapılabilir)", not ceiling_blocked),
    ]

    recent_low = float(d["Low"].tail(5).min())
    raw_support = max(float(r["ema20"]), recent_low)
    puan = sum(ok for _, ok in checks)
    toplam = len(checks)
    tek = puan / toplam * 100

    plan = compute_smart_plan(entry, raw_support, daily_atr, temel_puan, tek, is_swing=True, prev_close=prev_close)
    pos = calculate_position_size(
        plan.entry, plan.stop, plan.target1, params["capital"], params["risk_pct"],
        commission_rate=params["comm"], bsmv_rate=params["bsmv"], slippage_rate=params["slip"],
    )
    fp, _, _, _ = compute_flow(d1d, now)
    para_score = fp / 3 * 100

    parts = {"tek": tek, "para": para_score}
    if temel_puan is not None:
        parts["temel"] = float(temel_puan)
    tot_w = sum(SWING_WEIGHTS[k] for k in parts)
    genel = sum(SWING_WEIGHTS[k] * v for k, v in parts.items()) / tot_w

    return {
        "Hisse": t, "Fiyat": plan.entry, "Değişim": chg, "Kontroller": checks,
        "Puan": puan, "Toplam": toplam, "Tek": tek, "Para": para_score, "Temel": temel_puan, "Genel": genel,
        "Stop": plan.stop, "Risk": plan.risk_per_share, "Hedef1": plan.target1, "Hedef2": plan.target2,
        "Pos": pos, "IsWide": plan.is_wide, "PlanNote": plan.plan_note, "BandClamped": plan.band_clamped,
        "IsLive": is_live, "PriceSource": price_source, "UpdatedAt": updated_at or d.index[-1].strftime("%d.%m.%Y %H:%M"),
        "RVOL": rvol,
    }
