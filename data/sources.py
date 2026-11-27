from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
import time
from typing import Callable, Dict, Iterable, List, Optional, Tuple
import pandas as pd
import requests
import streamlit as st
import yfinance as yf
from config import (
    ISYATIRIM_DAILY_URL, ISYATIRIM_FIELD_MAP, ISYATIRIM_FUND_URL,
    MAX_FUNDAMENTAL_CANDIDATES, MAX_HEAVY_ANALYSIS_CANDIDATES, SCAN_TIME_BUDGET_SEC, TZ
)
from logger import get_logger

log = get_logger("data.sources")

try:
    from tvDatafeed import Interval as TvInterval, TvDatafeed
    HAS_TV_FEED = True
except Exception as exc:
    log.info("tvDatafeed yüklü değil veya başlatılamadı: %s", exc)
    HAS_TV_FEED = False

try:
    from tradingview_ta import Interval as TaInterval, TA_Handler
    HAS_TV_TA = True
except Exception as exc:
    log.info("tradingview_ta yüklü değil: %s", exc)
    HAS_TV_TA = False

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.isyatirim.com.tr/",
}


@dataclass
class SourceHealth:
    name: str
    ok: bool
    count: int
    last_bar_ts: Optional[str] = None
    age_minutes: Optional[float] = None
    error: Optional[str] = None


def _retry_call(fn: Callable, retries: int = 2, base_delay: float = 0.6):
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(base_delay * (2 ** attempt))
    raise last_exc


def normalize_ohlcv(df: Optional[pd.DataFrame]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={c: str(c).capitalize() for c in df.columns})
    req = ["Open", "High", "Low", "Close", "Volume"]
    if not all(c in df.columns for c in req):
        return pd.DataFrame()
    df = df[req].dropna(subset=["Close"])
    if df.empty:
        return pd.DataFrame()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    df.index = df.index.tz_localize("UTC").tz_convert(TZ) if df.index.tz is None else df.index.tz_convert(TZ)
    return df[~df.index.duplicated(keep="last")].sort_index()


def _calc_data_age_minutes(data_map: Dict[str, pd.DataFrame]) -> Tuple[Optional[str], Optional[float]]:
    if not data_map:
        return None, None
    latest = max(df.index[-1] for df in data_map.values() if not df.empty)
    now = pd.Timestamp.now(TZ)
    age_min = max(0.0, (now - latest).total_seconds() / 60.0)
    return latest.strftime("%d.%m.%Y %H:%M"), round(age_min, 1)


def fetch_yahoo_bulk(tickers: Iterable[str], period: str, interval: str) -> Tuple[Dict[str, pd.DataFrame], Optional[str]]:
    out: Dict[str, pd.DataFrame] = {}
    t_list = list(tickers)
    err_msg = None
    for i in range(0, len(t_list), 120):
        chunk = t_list[i:i + 120]
        try:
            raw = _retry_call(
                lambda: yf.download(
                    [t + ".IS" for t in chunk],
                    period=period,
                    interval=interval,
                    group_by="ticker",
                    progress=False,
                    threads=True,
                    auto_adjust=False,
                    timeout=14,
                ),
                retries=2,
            )
        except Exception as exc:
            err_msg = f"Yahoo toplu indirme hatası: {exc}"
            log.error(err_msg)
            continue
        if raw is None or raw.empty:
            continue
        for t in chunk:
            try:
                d = raw[t + ".IS"] if len(chunk) > 1 else raw
                norm = normalize_ohlcv(d)
                if len(norm) >= 30:
                    out[t] = norm
            except Exception as exc:
                log.debug("%s normalize hatası: %s", t, exc)
    return out, err_msg


def fetch_tv_history(tickers: Iterable[str], interval: str = "1d", n_bars: int = 260, limit: int = MAX_HEAVY_ANALYSIS_CANDIDATES) -> Tuple[Dict[str, pd.DataFrame], Optional[str]]:
    if not HAS_TV_FEED:
        return {}, "tvDatafeed kurulu değil"
    t_list = list(tickers)[:limit]
    if not t_list:
        return {}, None
    out: Dict[str, pd.DataFrame] = {}
    try:
        tv = TvDatafeed()
        tv_int = TvInterval.in_15_minute if interval == "15m" else TvInterval.in_daily
    except Exception as exc:
        msg = f"TvDatafeed oturum hatası: {exc}"
        log.warning(msg)
        return {}, msg

    def one(t: str):
        try:
            df = _retry_call(lambda: tv.get_hist(symbol=t, exchange="BIST", interval=tv_int, n_bars=n_bars), retries=1)
            norm = normalize_ohlcv(df)
            if len(norm) >= 30:
                return t, norm
        except Exception as exc:
            log.debug("TV hist hatası (%s): %s", t, exc)
        return t, None

    with ThreadPoolExecutor(6) as ex:
        for t, res in ex.map(one, t_list):
            if res is not None:
                out[t] = res
    return out, None


def fetch_isyatirim_daily(tickers: Iterable[str], limit: int = 50) -> Tuple[Dict[str, pd.DataFrame], Optional[str]]:
    """İş Yatırım günlük OHLCV çekimi (Uç nokta: DOĞRULANMADI)."""
    out: Dict[str, pd.DataFrame] = {}
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=400)
    s_str, e_str = start_dt.strftime("%d-%m-%Y"), end_dt.strftime("%d-%m-%Y")
    errors: List[str] = []

    def one(t: str):
        url = f"{ISYATIRIM_DAILY_URL}?hisse={t}&startdate={s_str}&enddate={e_str}"
        try:
            resp = _retry_call(lambda: requests.get(url, headers=HTTP_HEADERS, timeout=6), retries=1)
            resp.raise_for_status()
            payload = resp.json().get("value") or []
            if len(payload) < 30:
                return t, None
            rows = []
            for item in payload:
                dt_str = item.get("HGDG_TARIH")
                c = item.get("HGDG_KAPANIS")
                if dt_str and c is not None:
                    rows.append({
                        "Date": pd.to_datetime(dt_str, format="%d-%m-%Y"),
                        "Open": float(item.get("HGDG_AOF") or c),
                        "High": float(item.get("HGDG_MAX") or c),
                        "Low": float(item.get("HGDG_MIN") or c),
                        "Close": float(c),
                        "Volume": float(item.get("HGDG_HACIM") or 0),
                    })
            if len(rows) < 30:
                return t, None
            return t, normalize_ohlcv(pd.DataFrame(rows).set_index("Date"))
        except Exception as exc:
            errors.append(f"{t}: {exc}")
            return t, None

    with ThreadPoolExecutor(6) as ex:
        for t, res in ex.map(one, list(tickers)[:limit]):
            if res is not None and len(res) >= 30:
                out[t] = res

    err_summary = errors[0] if (errors and not out) else None
    if err_summary:
        log.warning("İş Yatırım günlük veri hatası: %s", err_summary)
    return out, err_summary


@st.cache_data(ttl=3600, show_spinner="BIST evreni yükleniyor...")
def get_daily_with_health(tickers: Tuple[str, ...]) -> Tuple[Dict[str, pd.DataFrame], List[SourceHealth]]:
    t0 = time.monotonic()
    health: List[SourceHealth] = []
    t_list = list(tickers)

    out, y_err = fetch_yahoo_bulk(t_list, "2y", "1d")
    ts_str, age = _calc_data_age_minutes(out)
    health.append(SourceHealth("Yahoo Finance (Günlük Toplu)", len(out) > 0, len(out), ts_str, age, y_err))

    missing = [t for t in t_list if t not in out]
    if missing and (time.monotonic() - t0) < SCAN_TIME_BUDGET_SEC:
        tv_out, tv_err = fetch_tv_history(missing, interval="1d", n_bars=500, limit=60)
        out.update(tv_out)
        if HAS_TV_FEED:
            ts_tv, age_tv = _calc_data_age_minutes(tv_out)
            health.append(SourceHealth("TradingView (Tamamlayıcı)", len(tv_out) > 0, len(tv_out), ts_tv, age_tv, tv_err))

    still_missing = [t for t in t_list if t not in out]
    if still_missing and (time.monotonic() - t0) < SCAN_TIME_BUDGET_SEC:
        is_out, is_err = fetch_isyatirim_daily(still_missing, limit=40)
        out.update(is_out)
        ts_is, age_is = _calc_data_age_minutes(is_out)
        health.append(SourceHealth("İş Yatırım (Yedek Günlük)", len(is_out) > 0, len(is_out), ts_is, age_is, is_err))

    return out, health


@st.cache_data(ttl=180, show_spinner="15 dakikalık grafikler alınıyor...")
def get_intraday_with_health(tickers: Tuple[str, ...]) -> Tuple[Dict[str, pd.DataFrame], SourceHealth]:
    t_list = list(tickers)[:MAX_HEAVY_ANALYSIS_CANDIDATES]
    out: Dict[str, pd.DataFrame] = {}
    err = None
    if HAS_TV_FEED:
        tv_out, err = fetch_tv_history(t_list, interval="15m", n_bars=200, limit=MAX_HEAVY_ANALYSIS_CANDIDATES)
        out.update(tv_out)
    missing = [t for t in t_list if t not in out]
    if missing:
        y_out, y_err = fetch_yahoo_bulk(missing, "5d", "15m")
        out.update(y_out)
        err = err or y_err
    ts_str, age = _calc_data_age_minutes(out)
    return out, SourceHealth("15 Dk Grafik Motoru", len(out) > 0, len(out), ts_str, age, err)


@st.cache_data(ttl=120)
def get_tv_realtime_snapshot(tickers: Tuple[str, ...]) -> Tuple[Dict[str, float], str, Optional[str]]:
    fetched_at = pd.Timestamp.now(TZ).strftime("%H:%M")
    if not HAS_TV_TA or not tickers:
        return {}, fetched_at, "tradingview-ta devre dışı"

    def one(t: str):
        try:
            handler = TA_Handler(symbol=t, screener="turkey", exchange="BIST", interval=TaInterval.INTERVAL_15_MINUTES)
            ind = handler.get_analysis().indicators
            close_p = ind.get("close")
            if close_p is not None and float(close_p) > 0:
                return t, float(close_p)
        except Exception as exc:
            log.debug("TV snapshot hatası (%s): %s", t, exc)
        return t, None

    snaps: Dict[str, float] = {}
    with ThreadPoolExecutor(8) as ex:
        for t, price in ex.map(one, list(tickers)[:MAX_HEAVY_ANALYSIS_CANDIDATES]):
            if price is not None:
                snaps[t] = price
    return snaps, fetched_at, None


def _extract_mapped_field(item: dict, field_key: str):
    for candidate in ISYATIRIM_FIELD_MAP.get(field_key, []):
        if candidate in item and item[candidate] is not None:
            return item[candidate]
    return None


@st.cache_data(ttl=43200)
def fetch_isyatirim_fundamental_map() -> Tuple[Dict[str, dict], SourceHealth]:
    """İş Yatırım bilanço tablosu (Uç nokta ve alan adları: DOĞRULANMADI)."""
    fmap: Dict[str, dict] = {}
    try:
        resp = _retry_call(lambda: requests.get(ISYATIRIM_FUND_URL, headers=HTTP_HEADERS, timeout=8), retries=2)
        resp.raise_for_status()
        items = resp.json().get("value") or []
        for item in items:
            code_raw = _extract_mapped_field(item, "code")
            if not code_raw:
                continue
            code = str(code_raw).strip().upper()
            roe = _extract_mapped_field(item, "returnOnEquity")
            pm = _extract_mapped_field(item, "profitMargins")
            eg = _extract_mapped_field(item, "earningsGrowth")
            fmap[code] = {
                "sector": _extract_mapped_field(item, "sector") or "",
                "trailingPE": _extract_mapped_field(item, "trailingPE"),
                "priceToBook": _extract_mapped_field(item, "priceToBook"),
                "returnOnEquity": (float(roe) / 100.0) if isinstance(roe, (int, float)) else None,
                "profitMargins": (float(pm) / 100.0) if isinstance(pm, (int, float)) else None,
                "earningsGrowth": (float(eg) / 100.0) if isinstance(eg, (int, float)) else None,
                "debtToEquity": _extract_mapped_field(item, "debtToEquity"),
                "_source": "İş Yatırım (DOĞRULANMADI Uç Nokta)",
            }
        return fmap, SourceHealth("İş Yatırım Bilanço", len(fmap) > 0, len(fmap), pd.Timestamp.now(TZ).strftime("%H:%M"), 0.0)
    except Exception as exc:
        msg = f"İş Yatırım bilanço erişim hatası: {exc}"
        log.warning(msg)
        return {}, SourceHealth("İş Yatırım Bilanço", False, 0, error=msg)


@st.cache_data(ttl=43200, show_spinner="Bilançolar kontrol ediliyor...")
def get_fundamentals_with_health(tickers: Tuple[str, ...]) -> Tuple[Dict[str, dict], SourceHealth]:
    is_map, health = fetch_isyatirim_fundamental_map()
    target = list(tickers)[:MAX_FUNDAMENTAL_CANDIDATES]

    def one(t: str):
        base = dict(is_map.get(t, {}))
        valid = [k for k in ("trailingPE", "priceToBook", "returnOnEquity", "profitMargins", "debtToEquity") if base.get(k) is not None]
        if len(valid) >= 3:
            return t, base
        try:
            yinfo = yf.Ticker(t + ".IS").info or {}
            for k in ("sector", "industry", "trailingPE", "priceToBook", "returnOnEquity", "profitMargins", "earningsGrowth", "debtToEquity"):
                if base.get(k) in (None, ""):
                    base[k] = yinfo.get(k)
            if not base.get("_source"):
                base["_source"] = "Yahoo Finance"
        except Exception as exc:
            log.debug("Yahoo bilanço hatası (%s): %s", t, exc)
        return t, base

    with ThreadPoolExecutor(8) as ex:
        res = dict(ex.map(one, target))
    return res, health
