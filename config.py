from __future__ import annotations
from typing import Dict, List, Tuple

TZ = "Europe/Istanbul"
APP_VERSION = "2.0.0"

# Bütçe ve Tarama Limitleri
MAX_HEAVY_ANALYSIS_CANDIDATES = 120
MAX_FUNDAMENTAL_CANDIDATES = 120
SCAN_TIME_BUDGET_SEC = 25.0

# Komisyon, BSMV ve Kayma Varsayılanları (Türkiye aracı kurum standartları)
DEFAULT_COMMISSION_RATE = 0.0005      # On binde 5 (%0.05)
DEFAULT_BSMV_RATE = 0.05              # Komisyon üzerinden %5 BSMV
DEFAULT_SLIPPAGE_RATE = 0.0010        # Tek yön %0.10 kayma

# Skor Ağırlıkları (Merkezi Config)
INTRADAY_WEIGHTS: Dict[str, float] = {"tek": 0.65, "para": 0.35}
SWING_WEIGHTS: Dict[str, float] = {"tek": 0.40, "temel": 0.35, "para": 0.25}

# Kalibre Edilmiş Skor Etiketleri (Tahmin gücü ima etmeyen karar destek etiketleri)
SCORE_LABELS: List[Tuple[float, str, str]] = [
    (75.0, "KRİTER UYUMU YÜKSEK", "#16a34a"),
    (60.0, "KRİTERLERE UYGUN", "#2563eb"),
    (0.0, "İZLEME / TEMKİNLİ", "#d97706"),
]

# Risk Profilleri: (min_rvol, chg_lo, chg_hi, rsi_lo, rsi_hi, min_tl_m, min_atr_pct)
PROFILES: Dict[str, Tuple[float, float, float, float, float, float, float]] = {
    "🛡️ Sakin ve Güvenli": (2.0, 1.5, 4.0, 50.0, 65.0, 100.0, 2.5),
    "⚖️ Dengeli (Önerilen)": (1.5, 1.5, 6.0, 50.0, 70.0, 100.0, 2.5),
    "🔥 Hızlı ve Hareketli": (1.2, 1.0, 7.0, 50.0, 75.0, 50.0, 2.0),
}

# DOĞRULANMADI: İş Yatırım dahili uç noktaları ve alan eşlemeleri
ISYATIRIM_DAILY_URL = "https://www.isyatirim.com.tr/_layouts/15/Isyatirim.Website/Common/Data.aspx/HisseTekil"
ISYATIRIM_FUND_URL = "https://www.isyatirim.com.tr/_layouts/15/Isyatirim.Website/Common/Data.aspx/HisseSenetleri"

ISYATIRIM_FIELD_MAP: Dict[str, List[str]] = {
    "code": ["HisseKodu", "Kod", "HISSE_KODU"],
    "sector": ["SektorAdi", "Sektor", "SEKTOR_ADI"],
    "trailingPE": ["FK", "FiyatKazanc"],
    "priceToBook": ["PDDD", "PiyasaDegeriDefterDegeri"],
    "returnOnEquity": ["OzsermayeKarliligi", "ROE"],
    "profitMargins": ["NetKarMarji"],
    "earningsGrowth": ["NetKarBuyume"],
    "debtToEquity": ["ToplamBorcOzsermaye", "BorcOzsermaye"],
}

# Varsayılan Tedbirli/Brüt Takas Yedek Listesi (KAP çekilemezse kullanılır)
FALLBACK_BANNED_TICKERS = {
    "DIRIT", "CASA", "COSMO", "EKIZ", "ETILR", "KUVVA",
    "MARKA", "MMCAS", "ROYAL", "SELGD", "UFUK", "UMPAS"
}

# BIST Resmi Tatil ve Yarım Gün (Arife) Takvimi (2025-2027)
BIST_HOLIDAYS = {
    "2025-01-01", "2025-03-30", "2025-03-31", "2025-04-01", "2025-04-23",
    "2025-05-01", "2025-05-19", "2025-06-06", "2025-06-07", "2025-06-08",
    "2025-06-09", "2025-07-15", "2025-08-30", "2025-10-29",
    "2026-01-01", "2026-03-20", "2026-03-21", "2026-03-22", "2026-04-23",
    "2026-05-01", "2026-05-19", "2026-05-27", "2026-05-28", "2026-05-29",
    "2026-05-30", "2026-07-15", "2026-08-30", "2026-10-29",
    "2027-01-01", "2027-03-09", "2027-03-10", "2027-03-11", "2027-04-23",
    "2027-05-01", "2027-05-16", "2027-05-17", "2027-05-18", "2027-05-19",
    "2027-07-15", "2027-08-30", "2027-10-29",
}

BIST_HALF_DAYS = {
    "2025-03-29", "2025-06-05", "2025-10-28",
    "2026-03-19", "2026-05-26", "2026-10-28",
    "2027-03-08", "2027-05-15", "2027-10-28",
}
