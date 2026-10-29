from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_DOWN

from django.db import transaction
from django.utils import timezone

from premium.models import (
    BankTransferRequest,
    PremiumEntitlement,
    PremiumRefundRequest,
)


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


@transaction.atomic
def complete_bank_transfer_refund(refund_request, *, completed_at=None):
    """관리자가 송금을 마친 계좌이체 환불 요청을 완료 처리한다."""
    completed_at = completed_at or timezone.now()
    locked_request = (
        PremiumRefundRequest.objects.select_for_update()
        .select_related("bank_transfer_request__user")
        .get(pk=refund_request.pk)
    )
    if locked_request.bank_transfer_request_id is None:
        raise RefundCalculationError("계좌이체 환불 요청이 아닙니다.")
    if locked_request.status == PremiumRefundRequest.Status.COMPLETED:
        return locked_request
    if locked_request.status == PremiumRefundRequest.Status.REJECTED:
        raise RefundCalculationError("거절된 환불 요청은 완료 처리할 수 없습니다.")

    transfer = BankTransferRequest.objects.select_for_update().get(
        pk=locked_request.bank_transfer_request_id,
    )
    entitlement = (
        PremiumEntitlement.objects.select_for_update()
        .filter(user=transfer.user)
        .first()
    )
    if (
        entitlement
        and entitlement.expires_at
        and entitlement.expires_at > completed_at
    ):
        unused_from = max(completed_at, transfer.entitlement_started_at)
        unused_duration = max(
            timedelta(0),
            transfer.entitlement_expires_at - unused_from,
        )
        entitlement.expires_at = max(
            completed_at,
            entitlement.expires_at - unused_duration,
        )
        entitlement.save(update_fields=["expires_at", "modified_at"])

    transfer.status = BankTransferRequest.Status.REFUNDED
    transfer.refunded_at = completed_at
    transfer.save(update_fields=["status", "refunded_at", "modified_at"])

    locked_request.status = PremiumRefundRequest.Status.COMPLETED
    locked_request.completed_at = completed_at
    locked_request.rejection_reason = ""
    locked_request.save(
        update_fields=[
            "status",
            "completed_at",
            "rejection_reason",
            "modified_at",
        ]
    )
    return locked_request
