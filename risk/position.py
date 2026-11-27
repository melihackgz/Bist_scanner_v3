from __future__ import annotations
from dataclasses import dataclass
from config import DEFAULT_BSMV_RATE, DEFAULT_COMMISSION_RATE, DEFAULT_SLIPPAGE_RATE


@dataclass
class PositionSizeResult:
    lot: int
    total_cost: float
    expected_stop_loss_tl: float
    expected_t1_gain_tl: float
    commission_roundtrip_tl: float
    affordable: bool
    reason: str


def calculate_position_size(
    entry: float,
    stop: float,
    target1: float,
    capital: float,
    risk_pct: float,
    max_position_weight: float = 0.35,
    commission_rate: float = DEFAULT_COMMISSION_RATE,
    bsmv_rate: float = DEFAULT_BSMV_RATE,
    slippage_rate: float = DEFAULT_SLIPPAGE_RATE,
) -> PositionSizeResult:
    """
    Komisyon, BSMV ve kayma maliyetlerini dahil ederek lot hesaplar.
    1 lot dahi maksimum risk limitini aşıyorsa lot=0 döndürür (zorla 1 lot önermez).
    """
    eff_comm = commission_rate * (1.0 + bsmv_rate)
    per_share_cost = (entry + stop) * (eff_comm + slippage_rate)
    true_risk_per_share = max(0.01, (entry - stop) + per_share_cost)

    max_tl_risk = capital * (risk_pct / 100.0)
    max_tl_alloc = capital * max_position_weight

    by_risk = int(max_tl_risk // true_risk_per_share)
    by_alloc = int(max_tl_alloc // max(entry * (1.0 + eff_comm), 0.01))
    lot = min(by_risk, by_alloc)

    if lot < 1:
        min_needed = true_risk_per_share / max(risk_pct / 100.0, 0.001)
        return PositionSizeResult(
            lot=0,
            total_cost=0.0,
            expected_stop_loss_tl=round(true_risk_per_share, 2),
            expected_t1_gain_tl=0.0,
            commission_roundtrip_tl=round(per_share_cost, 2),
            affordable=False,
            reason=f"Bu bütçe ve %{risk_pct:.2f} risk limiti ile 1 lot dahi uygun değil (1 lot riski: {true_risk_per_share:.2f} TL, gereken min. bütçe: ~{min_needed:,.0f} TL).",
        )

    total_cost = round(lot * entry * (1.0 + eff_comm), 2)
    stop_loss_tl = round(lot * true_risk_per_share, 2)
    t1_cost = (entry + target1) * (eff_comm + slippage_rate)
    t1_gain_tl = round(lot * ((target1 - entry) - t1_cost), 2)
    comm_rt = round(lot * per_share_cost, 2)

    return PositionSizeResult(
        lot=lot,
        total_cost=total_cost,
        expected_stop_loss_tl=stop_loss_tl,
        expected_t1_gain_tl=t1_gain_tl,
        commission_roundtrip_tl=comm_rt,
        affordable=True,
        reason="Risk ve bütçe limitlerine uygun.",
    )
