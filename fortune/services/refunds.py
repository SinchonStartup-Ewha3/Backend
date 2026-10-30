from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_DOWN

from django.db import transaction
from django.utils import timezone

from fortune.models import FortunePurchase, FortuneRefundRequest


PAYAPP_PAYMENT_KEY_PREFIX = "payapp:"


class FortuneRefundError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class FortuneRefundQuote:
    amount: int
    unused_days: int
    stop_from: date


def calculate_fortune_refund(purchase, *, requested_on):
    """요청 당일까지 사용하고 다음 날부터 남은 일수를 일할 계산한다."""
    if (
        purchase.active_from is None
        or purchase.active_until is None
        or purchase.active_from > requested_on
        or purchase.active_until <= requested_on
    ):
        raise FortuneRefundError(
            "NO_REFUNDABLE_FORTUNE_PURCHASE",
            "환불 가능한 잔여 운세 이용 기간이 없습니다.",
        )

    stop_from = requested_on + timedelta(days=1)
    unused_days = (purchase.active_until - stop_from).days + 1
    amount = int(
        (
            Decimal(purchase.amount)
            * Decimal(unused_days)
            / Decimal(purchase.duration_days)
        ).to_integral_value(rounding=ROUND_DOWN)
    )
    if unused_days < 1 or amount < 1:
        raise FortuneRefundError(
            "NO_REFUNDABLE_FORTUNE_PURCHASE",
            "환불 가능한 잔여 운세 이용 기간이 없습니다.",
        )

    return FortuneRefundQuote(
        amount=min(amount, purchase.amount),
        unused_days=unused_days,
        stop_from=stop_from,
    )


@transaction.atomic
def create_fortune_refund_request(
    *,
    purchase,
    user,
    reason,
    requested_on=None,
):
    requested_on = requested_on or timezone.localdate()
    locked_purchase = FortunePurchase.objects.select_for_update().get(
        pk=purchase.pk,
        user=user,
    )
    if not (locked_purchase.payment_key or "").startswith(
        PAYAPP_PAYMENT_KEY_PREFIX
    ):
        raise FortuneRefundError(
            "FORTUNE_REFUND_PAYAPP_ONLY",
            "PayApp으로 결제한 운세 이용권만 환불할 수 있습니다.",
        )
    if locked_purchase.payment_status != FortunePurchase.PaymentStatus.PAID:
        raise FortuneRefundError(
            "NO_REFUNDABLE_FORTUNE_PURCHASE",
            "환불 가능한 운세 결제 내역이 없습니다.",
        )
    if FortuneRefundRequest.objects.filter(purchase=locked_purchase).exists():
        raise FortuneRefundError(
            "FORTUNE_REFUND_ALREADY_EXISTS",
            "이미 환불을 요청한 운세 결제입니다.",
        )

    quote = calculate_fortune_refund(
        locked_purchase,
        requested_on=requested_on,
    )
    refund_request = FortuneRefundRequest.objects.create(
        user=user,
        purchase=locked_purchase,
        reason=reason,
        requested_amount=quote.amount,
        currency_code="KRW",
        unused_days=quote.unused_days,
        requested_on=requested_on,
        stop_from=quote.stop_from,
        original_active_until=locked_purchase.active_until,
    )

    # 요청 당일은 계속 사용하고 다음 날부터 자동으로 접근이 끝난다.
    locked_purchase.active_until = requested_on
    locked_purchase.save(update_fields=["active_until"])
    return refund_request


@transaction.atomic
def complete_fortune_refund(refund_request, *, completed_at=None):
    """PayApp 관리자에서 승인취소한 요청을 운영진 확인 후 완료한다."""
    completed_at = completed_at or timezone.now()
    locked_request = FortuneRefundRequest.objects.select_for_update().get(
        pk=refund_request.pk,
    )
    if locked_request.status == FortuneRefundRequest.Status.COMPLETED:
        return locked_request
    if locked_request.status == FortuneRefundRequest.Status.REJECTED:
        raise FortuneRefundError(
            "FORTUNE_REFUND_INVALID_STATE",
            "거절된 환불 요청은 완료 처리할 수 없습니다.",
        )

    purchase = FortunePurchase.objects.select_for_update().get(
        pk=locked_request.purchase_id,
    )
    if purchase.payment_status not in {
        FortunePurchase.PaymentStatus.PAID,
        FortunePurchase.PaymentStatus.REFUNDED,
    }:
        raise FortuneRefundError(
            "FORTUNE_REFUND_INVALID_STATE",
            "환불 완료 처리할 수 없는 결제 상태입니다.",
        )

    if purchase.payment_status != FortunePurchase.PaymentStatus.REFUNDED:
        purchase.payment_status = FortunePurchase.PaymentStatus.REFUNDED
        purchase.save(update_fields=["payment_status"])

    locked_request.status = FortuneRefundRequest.Status.COMPLETED
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


@transaction.atomic
def reject_fortune_refund(refund_request, *, reason, rejected_at=None):
    """환불 거절 시 심사 중 멈춘 기간만큼 이용 종료일을 뒤로 복원한다."""
    rejected_at = rejected_at or timezone.now()
    rejected_on = timezone.localtime(rejected_at).date()
    locked_request = FortuneRefundRequest.objects.select_for_update().get(
        pk=refund_request.pk,
    )
    if locked_request.status == FortuneRefundRequest.Status.COMPLETED:
        raise FortuneRefundError(
            "FORTUNE_REFUND_INVALID_STATE",
            "완료된 환불 요청은 거절할 수 없습니다.",
        )
    if locked_request.status == FortuneRefundRequest.Status.REJECTED:
        return locked_request

    purchase = FortunePurchase.objects.select_for_update().get(
        pk=locked_request.purchase_id,
    )
    if purchase.payment_status != FortunePurchase.PaymentStatus.PAID:
        raise FortuneRefundError(
            "FORTUNE_REFUND_INVALID_STATE",
            "이미 승인취소된 결제는 환불 거절 처리할 수 없습니다.",
        )

    paused_days = max(0, (rejected_on - locked_request.stop_from).days)
    purchase.active_until = (
        locked_request.original_active_until + timedelta(days=paused_days)
    )
    purchase.save(update_fields=["active_until"])

    if paused_days:
        upcoming = (
            FortunePurchase.objects.select_for_update()
            .filter(
                user_id=purchase.user_id,
                payment_status=FortunePurchase.PaymentStatus.PAID,
                active_from__gt=locked_request.original_active_until,
            )
            .exclude(pk=purchase.pk)
        )
        for queued_purchase in upcoming:
            queued_purchase.active_from += timedelta(days=paused_days)
            queued_purchase.active_until += timedelta(days=paused_days)
            queued_purchase.save(update_fields=["active_from", "active_until"])

    locked_request.status = FortuneRefundRequest.Status.REJECTED
    locked_request.rejection_reason = reason
    locked_request.rejected_at = rejected_at
    locked_request.save(
        update_fields=[
            "status",
            "rejection_reason",
            "rejected_at",
            "modified_at",
        ]
    )
    return locked_request
