from __future__ import annotations
from typing import Tuple
import numpy as np
import pandas as pd
from config import TZ


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    up, dn = d.clip(lower=0), -d.clip(upper=0)
    rs = up.ewm(alpha=1 / n, adjust=False).mean() / dn.ewm(alpha=1 / n, adjust=False).mean().replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["Close"].shift()
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def is_session_in_progress(now: pd.Timestamp | None = None) -> bool:
    now = now or pd.Timestamp.now(TZ)
    return now.weekday() < 5 and (9, 55) <= (now.hour, now.minute) < (18, 10)


def intraday_elapsed_fraction(now: pd.Timestamp | None = None) -> float:
    """BIST sürekli müzayede (10:00 - 18:00 = 480 dk) içinde geçen süre oranı."""
    now = now or pd.Timestamp.now(TZ)
    start = now.replace(hour=10, minute=0, second=0, microsecond=0)
    elapsed_min = max(15.0, min(480.0, (now - start).total_seconds() / 60.0))
    return elapsed_min / 480.0


def get_completed_daily_bars(df: pd.DataFrame, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Seans devam ediyorsa bugünün yarım günlük mumunu hariç tutar."""
    if df is None or df.empty:
        return pd.DataFrame()
    now = now or pd.Timestamp.now(TZ)
    if is_session_in_progress(now):
        return df[df.index.date < now.date()]
    return df


def compute_flow(df: pd.DataFrame, now: pd.Timestamp | None = None) -> Tuple[int, float, int, int]:
    """
    Tek kaynaklı para girişi (CMF + OBV + Kurumsal Birikim) hesabı.
    Hem tarama tablosunda hem tekil hisse analizinde tamamlanmış günleri kullanır.
    """
    completed = get_completed_daily_bars(df, now)
    if len(completed) < 25:
        return 0, 0.0, 0, 0
    d = completed.tail(60)
    hl = (d["High"] - d["Low"]).replace(0, np.nan)
    mfm = ((d["Close"] - d["Low"]) - (d["High"] - d["Close"])) / hl
    vol_sum = d["Volume"].tail(20).sum()
    cmf = float((mfm * d["Volume"]).tail(20).sum() / vol_sum) if vol_sum > 0 else 0.0
    obv = (np.sign(d["Close"].diff()).fillna(0) * d["Volume"]).cumsum()
    obv_up = bool(obv.iloc[-1] > obv.rolling(20).mean().iloc[-1])
    big = d["Volume"] > 1.5 * d["Volume"].rolling(20).mean().shift()
    acc = int((big & (d["Close"] > d["Open"])).tail(10).sum())
    dist = int((big & (d["Close"] < d["Open"])).tail(10).sum())
    pts = int(cmf > 0.05) + int(obv_up) + int(acc > dist)
    return pts, cmf, acc, dist


def check_wick_health(row: pd.Series) -> Tuple[bool, float]:
    high, low, open_, close = float(row["High"]), float(row["Low"]), float(row["Open"]), float(row["Close"])
    bar_range = high - low
    if bar_range <= 0:
        return True, 0.0
    upper_wick = high - max(open_, close)
    wick_ratio = upper_wick / bar_range
    return wick_ratio <= 0.45, wick_ratio * 100
