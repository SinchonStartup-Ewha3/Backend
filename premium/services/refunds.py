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


def _refund_user(refund_request):
    if refund_request.user_id:
        return refund_request.user
    if refund_request.purchase_id:
        return refund_request.purchase.user
    return refund_request.bank_transfer_request.user


def _refund_source(refund_request):
    return (
        refund_request.purchase
        if refund_request.purchase_id
        else refund_request.bank_transfer_request
    )


def _source_unused_duration(refund_request, at):
    source = _refund_source(refund_request)
    unused_from = max(at, source.entitlement_started_at)
    return max(
        timedelta(0),
        source.entitlement_expires_at - unused_from,
    )


@transaction.atomic
def suspend_refund_access(refund_request, *, suspended_at=None):
    """환불 심사 중 해당 결제에서 남은 프리미엄 기간을 일시 회수한다."""
    suspended_at = suspended_at or timezone.now()
    locked_request = (
        PremiumRefundRequest.objects.select_for_update()
        .select_related("user", "purchase__user", "bank_transfer_request__user")
        .get(pk=refund_request.pk)
    )
    if locked_request.access_suspended_at is not None:
        return locked_request

    user = _refund_user(locked_request)
    entitlement = (
        PremiumEntitlement.objects.select_for_update()
        .filter(user=user)
        .first()
    )
    if entitlement and entitlement.expires_at and entitlement.expires_at > suspended_at:
        suspended_duration = _source_unused_duration(
            locked_request,
            suspended_at,
        )
        entitlement.expires_at = max(
            suspended_at,
            entitlement.expires_at - suspended_duration,
        )
        entitlement.save(update_fields=["expires_at", "modified_at"])

    locked_request.access_suspended_at = suspended_at
    locked_request.save(update_fields=["access_suspended_at", "modified_at"])
    return locked_request


@transaction.atomic
def reject_refund_request(refund_request, *, reason, rejected_at=None):
    """환불 거절 시 요청 때 회수한 잔여 이용 시간을 사용자에게 복원한다."""
    rejected_at = rejected_at or timezone.now()
    locked_request = (
        PremiumRefundRequest.objects.select_for_update()
        .select_related("user", "purchase__user", "bank_transfer_request__user")
        .get(pk=refund_request.pk)
    )
    if locked_request.status == PremiumRefundRequest.Status.COMPLETED:
        raise RefundCalculationError("완료된 환불 요청은 거절할 수 없습니다.")
    if locked_request.status == PremiumRefundRequest.Status.REJECTED:
        return locked_request

    if (
        locked_request.access_suspended_at is not None
        and locked_request.access_restored_at is None
    ):
        user = _refund_user(locked_request)
        entitlement, _ = (
            PremiumEntitlement.objects.select_for_update()
            .get_or_create(user=user)
        )
        restored_duration = _source_unused_duration(
            locked_request,
            locked_request.access_suspended_at,
        )
        if entitlement.is_active(rejected_at):
            entitlement.expires_at += restored_duration
        else:
            entitlement.started_at = rejected_at
            entitlement.expires_at = rejected_at + restored_duration
        entitlement.save(
            update_fields=["started_at", "expires_at", "modified_at"],
        )
        locked_request.access_restored_at = rejected_at

    locked_request.status = PremiumRefundRequest.Status.REJECTED
    locked_request.rejection_reason = reason
    locked_request.save(
        update_fields=[
            "status",
            "rejection_reason",
            "access_restored_at",
            "modified_at",
        ]
    )
    return locked_request


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
        locked_request.access_suspended_at is None
        and entitlement
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
