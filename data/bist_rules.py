from __future__ import annotations
import json
import math
from pathlib import Path
from typing import Set, Tuple
import pandas as pd
import requests
from config import BIST_HALF_DAYS, BIST_HOLIDAYS, FALLBACK_BANNED_TICKERS, TZ
from logger import get_logger

log = get_logger("bist_rules")
BANNED_CACHE_FILE = Path(__file__).resolve().parent.parent / "banned_cache.json"

# Borsa İstanbul Pay Piyasası Fiyat Adımı Tablosu (BIST Yönergesi)
TICK_TABLE = [
    (20.00, 0.01),
    (50.00, 0.02),
    (100.00, 0.05),
    (250.00, 0.10),
    (500.00, 0.25),
    (1000.00, 0.50),
    (2500.00, 1.00),
    (float("inf"), 2.50),
]


def get_tick_size(price: float) -> float:
    p = max(0.01, float(price))
    for upper, step in TICK_TABLE:
        if p < upper:
            return step
    return 2.50


def round_to_tick(price: float, direction: str = "nearest") -> float:
    p = max(0.01, float(price))
    step = get_tick_size(p)
    ratio = p / step
    if direction == "down":
        ticks = math.floor(ratio + 1e-9)
    elif direction == "up":
        ticks = math.ceil(ratio - 1e-9)
    else:
        ticks = round(ratio)
    return round(max(step, ticks * step), 2)


def get_bist_daily_limits(prev_close: float) -> Tuple[float, float]:
    """Önceki kapanışa göre BIST ±%10 taban ve tavan fiyatlarını geçerli adıma yuvarlar."""
    floor_p = round_to_tick(prev_close * 0.90, direction="up")
    ceil_p = round_to_tick(prev_close * 1.10, direction="down")
    return floor_p, ceil_p


def is_at_ceiling(price: float, prev_close: float) -> bool:
    if prev_close <= 0:
        return False
    _, ceil_p = get_bist_daily_limits(prev_close)
    return round_to_tick(price, "nearest") >= ceil_p


def clamp_to_bist_band(price: float, prev_close: float) -> Tuple[float, bool]:
    floor_p, ceil_p = get_bist_daily_limits(prev_close)
    if price < floor_p:
        return floor_p, True
    if price > ceil_p:
        return ceil_p, True
    return price, False


def bist_market_status(now: pd.Timestamp | None = None) -> Tuple[str, str]:
    now = now or pd.Timestamp.now(TZ)
    d_str = now.strftime("%Y-%m-%d")
    hm = (now.hour, now.minute)

    if now.weekday() >= 5 or d_str in BIST_HOLIDAYS:
        return "closed", "BIST bugün kapalı (Hafta sonu / Resmi-Dini Tatil). Veriler son işlem gününe aittir."

    is_half = d_str in BIST_HALF_DAYS
    close_hm = (12, 40) if is_half else (18, 10)
    if hm < (9, 40) or hm > close_hm:
        return "closed", "Borsa şu an kapalı. Görünen rakamlar son işlem gününe aittir."
    if is_half and hm >= (12, 15):
        return "late", "Arife (yarım gün) seansı kapanmak üzere (12:40). Yeni işlem açmayın."
    if hm < (10, 15):
        return "early", "Açılış seansı / ilk 15 dk oynaklığı yüksek. 10:15 sonrası daha sağlıklıdır."
    if (18, 0) <= hm <= (18, 10):
        return "late", "Kapanış seansı (18:00–18:10) aktif; yalnızca kapanış fiyatından eşleşme yapılır."
    if hm >= (17, 30):
        return "late", "Seans kapanışına 30 dakikadan az kaldı. Gün içi işlemleri kapatma zamanı."
    return "open", "BIST sürekli müzayede seansı açık."


def fetch_banned_tickers_with_fallback() -> Tuple[Set[str], str]:
    """
    KAP / BIST VBTS tedbirli hisse listesini çekmeyi dener.
    NOT: Resmi KAP JSON uç noktası DOĞRULANMADI; erişilemezse yerel önbellek veya yedek listeye düşer.
    """
    try:
        resp = requests.get("https://www.kap.org.tr/tr/bildirim-sorgu", timeout=4, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200 and BANNED_CACHE_FILE.exists():
            cached = json.loads(BANNED_CACHE_FILE.read_text(encoding="utf-8"))
            if cached.get("tickers"):
                return set(cached["tickers"]), f"Yerel KAP Önbelleği ({cached.get('updated_at', '-')})"
    except Exception as exc:
        log.info("KAP tedbir listesi otomatik çekilemedi (yedek liste kullanılıyor): %s", exc)

    return set(FALLBACK_BANNED_TICKERS), "Manuel / Varsayılan Yedek Liste (Otomatik KAP çekimi doğrulanmadı)"
