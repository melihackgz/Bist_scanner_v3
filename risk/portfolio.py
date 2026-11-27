from __future__ import annotations
from collections import Counter
from typing import Dict, List
import pandas as pd


def evaluate_portfolio_risk(
    open_trades: pd.DataFrame,
    capital: float,
    sector_map: Dict[str, str],
    max_open_positions: int = 5,
    max_total_risk_pct: float = 4.0,
) -> dict:
    if open_trades is None or open_trades.empty:
        return {"open_count": 0, "total_risk_tl": 0.0, "total_risk_pct": 0.0, "warnings": [], "can_open_new": True}

    warnings: List[str] = []
    open_count = len(open_trades)
    total_risk_tl = float(((open_trades["entry"] - open_trades["stop"]).clip(lower=0) * open_trades["lot"]).sum())
    total_risk_pct = (total_risk_tl / max(capital, 1.0)) * 100.0

    if open_count >= max_open_positions:
        warnings.append(f"Maksimum eş zamanlı pozisyon sınırına ({max_open_positions}) ulaşıldı.")
    if total_risk_pct >= max_total_risk_pct:
        warnings.append(f"Portföy toplam açık stop riski (%{total_risk_pct:.2f}) üst sınırı (%{max_total_risk_pct:.1f}) aştı.")

    sectors = [sector_map.get(t, "Bilinmiyor") for t in open_trades["ticker"] if sector_map.get(t)]
    for sec, cnt in Counter(sectors).items():
        if cnt >= 2:
            warnings.append(f"Sektör yoğunlaşması: '{sec}' sektöründe {cnt} açık pozisyon mevcut.")

    return {
        "open_count": open_count,
        "total_risk_tl": round(total_risk_tl, 2),
        "total_risk_pct": round(total_risk_pct, 2),
        "warnings": warnings,
        "can_open_new": (open_count < max_open_positions) and (total_risk_pct < max_total_risk_pct),
    }
