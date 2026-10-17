from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN


class RefundCalculationError(Exception):
    pass


@dataclass(frozen=True)
class ProratedRefund:
    amount: int
    remaining_seconds: int


def calculate_prorated_refund(purchase, *, requested_at):
    """구매 이용 기간 중 요청 시점에 남은 기간만 원 단위 내림으로 환불한다."""
    starts_at = purchase.entitlement_started_at
    expires_at = purchase.entitlement_expires_at
    if starts_at is None or expires_at is None or starts_at >= expires_at:
        raise RefundCalculationError("환불 금액을 계산할 이용 기간이 없습니다.")

    unused_from = max(requested_at, starts_at)
    total_seconds = Decimal(str((expires_at - starts_at).total_seconds()))
    remaining = max(
        Decimal("0"),
        Decimal(str((expires_at - unused_from).total_seconds())),
    )
    remaining_seconds = int(remaining.to_integral_value(rounding=ROUND_DOWN))
    amount = int(
        (Decimal(purchase.amount) * remaining / total_seconds).to_integral_value(
            rounding=ROUND_DOWN
        )
    )
    if amount < 1 or remaining_seconds < 1:
        raise RefundCalculationError("환불 가능한 잔여 이용 기간이 없습니다.")

    return ProratedRefund(
        amount=min(amount, purchase.amount),
        remaining_seconds=remaining_seconds,
    )
