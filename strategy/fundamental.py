from __future__ import annotations
from typing import List, Optional, Tuple


def _ok_num(x) -> bool:
    return x is not None and isinstance(x, (int, float)) and x == x


def normalize_debt_to_equity(raw_dte: Optional[float]) -> Optional[float]:
    """Yahoo Finance bazen %140 yerine 140.0, İş Yatırım ise 1.40 döner; orana normalize eder."""
    if not _ok_num(raw_dte) or raw_dte < 0:
        return None
    return float(raw_dte) / 100.0 if raw_dte > 10.0 else float(raw_dte)


def classify_bist_sector(sector_text: str) -> str:
    s = (sector_text or "").lower()
    if any(k in s for k in ("bank", "finans", "sigorta", "leasing", "faktoring", "aracı")):
        return "FINANS"
    if any(k in s for k in ("gyo", "gayrimenkul", "reit", "real estate")):
        return "GYO"
    if any(k in s for k in ("holding", "yatırım ortak")):
        return "HOLDING"
    return "SANAYI"


def compute_fundamental_score(info: dict) -> Tuple[Optional[int], int, List[tuple], str]:
    """
    Sektöre özel ve TMS 29 enflasyon muhasebesi / yüksek nominal faiz ortamına
    kalibre edilmiş bilanço puanlaması.
    """
    sector_raw = str(info.get("sector") or info.get("industry") or "")
    sec_type = classify_bist_sector(sector_raw)

    pe = info.get("trailingPE")
    pb = info.get("priceToBook")
    roe = info.get("returnOnEquity")
    pm = info.get("profitMargins")
    eg = info.get("earningsGrowth")
    dte = normalize_debt_to_equity(info.get("debtToEquity"))

    if sec_type == "FINANS":
        items = [
            ("Fiyat / Kazanç (Banka Eşiği <= 10)", pe, 25, lambda v: 0 < v <= 10, lambda v: f"{v:.1f}", "10 ve altı"),
            ("Piyasa / Defter Değeri (<= 1.8)", pb, 30, lambda v: 0 < v <= 1.8, lambda v: f"{v:.2f}", "1.8 ve altı"),
            ("Özkaynak Kârlılığı (Enflasyon Uyumlu >= %25)", roe, 30, lambda v: v >= 0.25, lambda v: f"%{v*100:.0f}", "%25 ve üzeri"),
            ("Kâr Büyümesi (Pozitif)", eg, 15, lambda v: v > 0, lambda v: f"%{v*100:.0f}", "Pozitif"),
        ]
    elif sec_type in ("GYO", "HOLDING"):
        items = [
            ("Piyasa / Defter Değeri (İskonto <= 1.3)", pb, 35, lambda v: 0 < v <= 1.3, lambda v: f"{v:.2f}", "1.3 ve altı"),
            ("Fiyat / Kazanç (<= 15)", pe, 20, lambda v: 0 < v <= 15, lambda v: f"{v:.1f}", "15 ve altı"),
            ("Özkaynak Kârlılığı (>= %18)", roe, 25, lambda v: v >= 0.18, lambda v: f"%{v*100:.0f}", "%18 ve üzeri"),
            ("Net Borç / Özkaynak (<= 1.2x)", dte, 20, lambda v: v <= 1.2, lambda v: f"{v:.2f}x", "1.2x ve altı"),
        ]
    else:
        items = [
            ("Fiyat / Kazanç (<= 18)", pe, 20, lambda v: 0 < v <= 18, lambda v: f"{v:.1f}", "18 ve altı"),
            ("Piyasa / Defter Değeri (<= 3.5)", pb, 15, lambda v: 0 < v <= 3.5, lambda v: f"{v:.2f}", "3.5 ve altı"),
            ("Özkaynak Kârlılığı (Nominal >= %22)", roe, 25, lambda v: v >= 0.22, lambda v: f"%{v*100:.0f}", "%22 ve üzeri"),
            ("Net Kâr Marjı (>= %8)", pm, 15, lambda v: v >= 0.08, lambda v: f"%{v*100:.0f}", "%8 ve üzeri"),
            ("Kâr Büyümesi (Pozitif)", eg, 10, lambda v: v > 0, lambda v: f"%{v*100:.0f}", "Pozitif"),
            ("Borç / Özkaynak Oranı (<= 1.5x)", dte, 15, lambda v: v <= 1.5, lambda v: f"{v:.2f}x", "1.5x ve altı"),
        ]

    pts = mx = 0
    rows = []
    for name, v, w, test, fmt, rule in items:
        if _ok_num(v):
            mx += w
            good = bool(test(v))
            pts += w if good else 0
            rows.append((name, fmt(v), rule, good))

    score = round(pts / mx * 100) if mx >= 40 else None
    return score, mx, rows, sec_type
