from __future__ import annotations
from typing import Tuple
import pandas as pd


def detect_unadjusted_split_anomaly(df: pd.DataFrame) -> Tuple[bool, str]:
    """
    Bedelsiz sermaye artırımı veya temettü sonrası düzeltilmemiş fiyat serilerinde
    oluşan yapay %35+ tek günlük gap'leri tespit eder.
    """
    if df is None or len(df) < 15:
        return False, ""
    recent = df.tail(30)
    pct = recent["Close"].pct_change().dropna()
    extreme = pct[pct < -0.35]
    if not extreme.empty:
        dt_str = extreme.index[-1].strftime("%d.%m.%Y")
        drop_pct = float(extreme.iloc[-1]) * 100
        return True, f"{dt_str} tarihinde %{drop_pct:.1f} ani fiyat düşüşü (olası bedelsiz/temettü düzeltme farkı) tespit edildi."
    return False, ""
