"""Cron / GitHub Actions ile arka planda çalıştırılıp sonuçları SQLite'a yazan zamanlayıcı görevi."""
import sqlite3
import pandas as pd
from config import PROFILES, TZ
from data.bist_rules import fetch_banned_tickers_with_fallback
from data.sources import get_daily_with_health
from data.universe import load_universe
from logger import get_logger
from storage.repository import DB_PATH, init_db
from strategy.analyzer import build_daily_summary_table

log = get_logger("scheduled_scan")


def run_background_scan():
    init_db()
    uni = load_universe()
    banned, _ = fetch_banned_tickers_with_fallback()
    daily, _ = get_daily_with_health(tuple(uni.tickers))
    _, _, _, _, _, min_tl, min_atr = PROFILES["⚖️ Dengeli (Önerilen)"]
    dtab = build_daily_summary_table(daily, min_tl, min_atr, banned)
    passed = dtab[dtab["Geçti"]].sort_values("İşlem (M TL)", ascending=False).head(30)

    now_iso = pd.Timestamp.now(TZ).isoformat(timespec="seconds")
    with sqlite3.connect(DB_PATH) as conn:
        for _, row in passed.iterrows():
            conn.execute(
                """INSERT INTO scan_snapshots (scanned_at, mode, ticker, price, stop, target1, score, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (now_iso, "Arka Plan Tarama", row["Hisse"], row["Kapanış"], round(row["Kapanış"] - row["DailyATR"], 2), round(row["Kapanış"] + 2 * row["DailyATR"], 2), 70.0, "ScheduledJob"),
            )
    log.info("Arka plan taraması tamamlandı: %d aday kaydedildi.", len(passed))


if __name__ == "__main__":
    run_background_scan()
