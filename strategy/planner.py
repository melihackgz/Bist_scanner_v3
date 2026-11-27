from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from data.bist_rules import clamp_to_bist_band, round_to_tick


@dataclass
class TradePlan:
    entry: float
    stop: float
    risk_per_share: float
    target1: float
    target2: float
    is_wide: bool
    plan_note: str
    rr1: float
    rr2: float
    band_clamped: bool = False


def compute_smart_plan(
    entry: float,
    raw_support: float,
    daily_atr: float,
    temel_puan: Optional[float],
    tek_puan: float,
    is_swing: bool,
    prev_close: Optional[float] = None,
) -> TradePlan:
    """Canlı tarama ve backtest motorunun ortak kullandığı tek kaynaklı stop/hedef motoru."""
    if is_swing and temel_puan is not None:
        if temel_puan >= 65:
            atr_buffer, rr1, rr2 = 0.65, 2.2, 3.8
            plan_note = f"Bilanço güçlü ({temel_puan:.0f}/100): Destek payı korundu, hedefler genişletildi."
        elif temel_puan >= 45:
            atr_buffer, rr1, rr2 = 0.50, 1.8, 3.0
            plan_note = f"Bilanço orta ({temel_puan:.0f}/100): Standart teknik destek ve hedefler uygulandı."
        else:
            atr_buffer, rr1, rr2 = 0.35, 1.4, 2.2
            plan_note = f"Bilanço zayıf ({temel_puan:.0f}/100): Stop sıkılaştırıldı, hedefler yakın tutuldu."
    else:
        atr_buffer = 0.30 if not is_swing else 0.50
        rr1 = 1.6 if tek_puan >= 80 else 1.4
        rr2 = 2.6 if tek_puan >= 80 else 2.2
        plan_note = "Teknik destek (EMA/VWAP) ve günlük ATR baz alınarak hesaplandı."

    stop = raw_support - atr_buffer * daily_atr
    min_stop_dist = 0.35 * daily_atr
    if (entry - stop) < min_stop_dist:
        stop = entry - min_stop_dist

    max_stop_dist = (1.8 * daily_atr) if is_swing else (0.9 * daily_atr)
    is_wide_warning = False
    if (entry - stop) > max_stop_dist:
        is_wide_warning = True
        stop = entry - max_stop_dist

    entry_tick = round_to_tick(entry, direction="nearest")
    stop_tick = round_to_tick(stop, direction="down")
    if stop_tick >= entry_tick:
        stop_tick = round_to_tick(entry_tick - max(0.01, 0.35 * daily_atr), direction="down")

    risk = max(entry_tick - stop_tick, 0.01)
    t1_tick = round_to_tick(entry_tick + rr1 * risk, direction="up")
    t2_tick = round_to_tick(entry_tick + rr2 * risk, direction="up")

    band_clamped = False
    if prev_close is not None and prev_close > 0:
        stop_c, c1 = clamp_to_bist_band(stop_tick, prev_close)
        t1_c, c2 = clamp_to_bist_band(t1_tick, prev_close)
        t2_c, c3 = clamp_to_bist_band(t2_tick, prev_close)
        if not is_swing:
            stop_tick, t1_tick, t2_tick = stop_c, t1_c, t2_c
            band_clamped = any((c1, c2, c3))

    return TradePlan(
        entry=entry_tick,
        stop=stop_tick,
        risk_per_share=round(max(entry_tick - stop_tick, 0.01), 4),
        target1=t1_tick,
        target2=t2_tick,
        is_wide=is_wide_warning,
        plan_note=plan_note,
        rr1=rr1,
        rr2=rr2,
        band_clamped=band_clamped,
    )
