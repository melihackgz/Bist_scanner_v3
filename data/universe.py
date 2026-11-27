from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List
import requests
from config import ISYATIRIM_FUND_URL, ISYATIRIM_FIELD_MAP
from logger import get_logger

log = get_logger("universe")
UNIVERSE_FILE = Path(__file__).resolve().parent.parent / "hisseler.txt"


@dataclass
class UniverseLoadResult:
    tickers: List[str]
    source: str
    warning: str | None = None


def load_universe() -> UniverseLoadResult:
    """hisseler.txt dosyasını okur; yoksa veya bozuksa kullanıcıyı uyararak yedek listeye geçer."""
    if UNIVERSE_FILE.exists():
        try:
            raw = UNIVERSE_FILE.read_text(encoding="utf-8").upper().split()
            cleaned = sorted({t.strip().replace(".IS", "") for t in raw if t.strip().isalpha() and 3 <= len(t.strip()) <= 6})
            if len(cleaned) >= 50:
                return UniverseLoadResult(tickers=cleaned, source=f"hisseler.txt ({len(cleaned)} sembol)")
            warn = f"hisseler.txt dosyasında yalnızca {len(cleaned)} geçerli sembol bulundu (beklenen >=50)."
            log.warning(warn)
        except Exception as exc:
            warn = f"hisseler.txt okunamadı: {exc}"
            log.error(warn)
    else:
        warn = "hisseler.txt dosyası bulunamadı. Otomatik güncelleme veya 16 hisseli acil yedek liste kullanılacak."
        log.warning(warn)

    fallback = [
        "AKBNK", "ARCLK", "ASELS", "BIMAS", "EREGL", "FROTO", "GARAN", "ISCTR",
        "KCHOL", "SAHOL", "SISE", "TCELL", "THYAO", "TOASO", "TUPRS", "YKBNK"
    ]
    return UniverseLoadResult(tickers=fallback, source="Acil Yedek Liste (16 sembol)", warning=warn)


def refresh_universe_from_web() -> tuple[bool, str]:
    """İş Yatırım hisse listesinden evreni otomatik günceller (DOĞRULANMADI uç nokta)."""
    try:
        resp = requests.get(ISYATIRIM_FUND_URL, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        items = resp.json().get("value") or []
        codes = set()
        for it in items:
            for key in ISYATIRIM_FIELD_MAP["code"]:
                val = it.get(key)
                if val and isinstance(val, str) and val.strip().isalpha():
                    codes.add(val.strip().upper())
                    break
        if len(codes) >= 100:
            sorted_codes = sorted(codes)
            UNIVERSE_FILE.write_text("\n".join(sorted_codes) + "\n", encoding="utf-8")
            log.info("Evren güncellendi: %d hisse", len(sorted_codes))
            return True, f"{len(sorted_codes)} BIST hissesi hisseler.txt dosyasına kaydedildi."
        return False, "Uzak kaynaktan yeterli sayıda BIST kodu alınamadı."
    except Exception as exc:
        log.error("Evren güncelleme hatası: %s", exc)
        return False, f"Güncelleme başarısız: {exc}"
