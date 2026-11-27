from __future__ import annotations
from io import BytesIO
from pathlib import Path
import sqlite3
from typing import Optional
import pandas as pd
from config import TZ
from exceptions import ValidationError

DB_PATH = Path(__file__).resolve().parent.parent / "journal.db"
CURRENT_SCHEMA_VERSION = 2


def _now_iso() -> str:
    return pd.Timestamp.now(TZ).isoformat(timespec="seconds")


def init_db(db_path: Path = DB_PATH) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER PRIMARY KEY)")
        cur_v = conn.execute("SELECT MAX(version) FROM schema_meta").fetchone()[0] or 0

        if cur_v < 1:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    entry REAL NOT NULL,
                    stop REAL NOT NULL,
                    target1 REAL NOT NULL,
                    target2 REAL NOT NULL,
                    lot INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'AÇIK',
                    exit_price REAL,
                    pnl REAL
                )
            """)
            cur_v = 1

        if cur_v < 2:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(trades)").fetchall()}
            if "partial_t1_taken" not in cols:
                conn.execute("ALTER TABLE trades ADD COLUMN partial_t1_taken INTEGER NOT NULL DEFAULT 0")
            if "notes" not in cols:
                conn.execute("ALTER TABLE trades ADD COLUMN notes TEXT DEFAULT ''")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scan_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scanned_at TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    price REAL NOT NULL,
                    stop REAL NOT NULL,
                    target1 REAL NOT NULL,
                    score REAL NOT NULL,
                    source TEXT NOT NULL
                )
            """)
            cur_v = 2

        conn.execute("DELETE FROM schema_meta")
        conn.execute("INSERT INTO schema_meta (version) VALUES (?)", (CURRENT_SCHEMA_VERSION,))


def add_trade(mode: str, ticker: str, entry: float, stop: float, t1: float, t2: float, lot: int, db_path: Path = DB_PATH) -> None:
    if lot < 1:
        raise ValidationError("0 lot ile işlem kaydedilemez. Bütçe veya risk limitinizi kontrol edin.")
    if stop >= entry:
        raise ValidationError("Zarar kes (stop) fiyatı alış fiyatından düşük olmalıdır.")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """INSERT INTO trades (created_at, mode, ticker, entry, stop, target1, target2, lot, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'AÇIK')""",
            (_now_iso(), mode, ticker.upper(), round(entry, 2), round(stop, 2), round(t1, 2), round(t2, 2), int(lot)),
        )


def get_trades(db_path: Path = DB_PATH) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query("SELECT * FROM trades ORDER BY id DESC", conn)


def update_trade_status(
    trade_id: int,
    status: str,
    exit_price: Optional[float] = None,
    new_entry: Optional[float] = None,
    new_lot: Optional[int] = None,
    partial_t1_taken: bool = False,
    db_path: Path = DB_PATH,
) -> None:
    is_open = status == "AÇIK"
    if is_open and exit_price is not None and exit_price > 0:
        raise ValidationError("Durum 'AÇIK' iken satış fiyatı girilemez. Önce durumu kapalı seçin.")
    if not is_open and (exit_price is None or exit_price <= 0):
        raise ValidationError("Kapatılan işlem için 0'dan büyük bir satış fiyatı girmelisiniz.")

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT entry, lot FROM trades WHERE id = ?", (trade_id,)).fetchone()
        if not row:
            raise ValidationError("Kayıt bulunamadı.")
        entry_val = round(float(new_entry), 2) if (new_entry is not None and new_entry > 0) else float(row[0])
        lot_val = int(new_lot) if (new_lot is not None and new_lot > 0) else int(row[1])
        pnl = None if is_open else round((float(exit_price) - entry_val) * lot_val, 2)
        conn.execute(
            """UPDATE trades
               SET entry = ?, lot = ?, status = ?, exit_price = ?, pnl = ?, partial_t1_taken = ?
               WHERE id = ?""",
            (entry_val, lot_val, status, None if is_open else round(float(exit_price), 2), pnl, int(partial_t1_taken), trade_id),
        )


def delete_trade(trade_id: int, db_path: Path = DB_PATH) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM trades WHERE id = ?", (trade_id,))


def export_df_to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Veriler")
    return buf.getvalue()
