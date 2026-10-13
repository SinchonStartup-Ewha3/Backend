from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from premium.models import (
    PaddleWebhookEvent,
    PremiumEntitlement,
    PremiumPurchase,
)


class PaddleWebhookValidationError(Exception):
    pass


def _event_time(payload):
    value = parse_datetime(payload.get("occurred_at", ""))
    if value is None:
        raise PaddleWebhookValidationError("occurred_at이 올바르지 않습니다.")
    return value


def _find_purchase(transaction_id):
    if not transaction_id:
        return None
    return (
        PremiumPurchase.objects.select_for_update()
        .select_related("user")
        .filter(paddle_transaction_id=transaction_id)
        .first()
    )


def _validate_completed_transaction(purchase, data):
    if data.get("status") != "completed":
        raise PaddleWebhookValidationError("완료 이벤트의 거래 상태가 completed가 아닙니다.")
    if data.get("subscription_id"):
        raise PaddleWebhookValidationError("일회성 상품에 subscription_id가 포함되었습니다.")

    custom_data = data.get("custom_data") or {}
    if (
        str(custom_data.get("wee_purchase_id")) != str(purchase.pk)
        or str(custom_data.get("wee_user_id")) != str(purchase.user_id)
    ):
        raise PaddleWebhookValidationError("Paddle 거래의 사용자 연결 정보가 일치하지 않습니다.")

    if data.get("currency_code") != settings.PADDLE_PREMIUM_CURRENCY:
        raise PaddleWebhookValidationError("Paddle 거래 통화가 일치하지 않습니다.")

    totals = ((data.get("details") or {}).get("totals") or {})
    total = totals.get("grand_total", totals.get("total"))
    if str(total) != str(settings.PADDLE_PREMIUM_AMOUNT):
        raise PaddleWebhookValidationError("Paddle 거래 결제 금액이 일치하지 않습니다.")

    items = data.get("items") or []
    if len(items) != 1:
        raise PaddleWebhookValidationError("Paddle 거래 상품 수가 일치하지 않습니다.")
    item = items[0]
    price = item.get("price") or {}
    if price.get("id") != settings.PADDLE_PRICE_ID or item.get("quantity") != 1:
        raise PaddleWebhookValidationError("Paddle 거래 상품 또는 수량이 일치하지 않습니다.")

    if (
        purchase.paddle_price_id != settings.PADDLE_PRICE_ID
        or purchase.amount != settings.PADDLE_PREMIUM_AMOUNT
        or purchase.currency_code != settings.PADDLE_PREMIUM_CURRENCY
    ):
        raise PaddleWebhookValidationError("서버에 저장된 구매 정보가 상품 설정과 일치하지 않습니다.")
    return price


def _grant_entitlement(purchase, data, occurred_at):
    price = _validate_completed_transaction(purchase, data)
    if purchase.entitlement_expires_at is not None:
        return
    if purchase.status in {
        PremiumPurchase.Status.CANCELED,
        PremiumPurchase.Status.REFUNDED,
        PremiumPurchase.Status.CHARGEBACK,
    }:
        return
    if purchase.user is None:
        raise PaddleWebhookValidationError("탈퇴한 사용자의 거래에는 권한을 지급할 수 없습니다.")

    entitlement, _ = PremiumEntitlement.objects.select_for_update().get_or_create(
        user=purchase.user,
    )
    if entitlement.expires_at and entitlement.expires_at > occurred_at:
        grant_start = entitlement.expires_at
    else:
        grant_start = occurred_at
        entitlement.started_at = occurred_at
    grant_end = grant_start + timedelta(days=settings.PADDLE_PREMIUM_DURATION_DAYS)

    entitlement.expires_at = grant_end
    entitlement.save(update_fields=["started_at", "expires_at", "modified_at"])

    purchase.status = (
        PremiumPurchase.Status.PARTIALLY_REFUNDED
        if purchase.status == PremiumPurchase.Status.PARTIALLY_REFUNDED
        else PremiumPurchase.Status.COMPLETED
    )
    purchase.paddle_customer_id = data.get("customer_id") or ""
    purchase.paddle_product_id = (price.get("product_id") or "")
    purchase.completed_at = occurred_at
    purchase.entitlement_started_at = grant_start
    purchase.entitlement_expires_at = grant_end
    purchase.failure_reason = ""
    purchase.save(
        update_fields=[
            "status",
            "paddle_customer_id",
            "paddle_product_id",
            "completed_at",
            "entitlement_started_at",
            "entitlement_expires_at",
            "failure_reason",
            "modified_at",
        ]
    )


def _mark_transaction_state(data, event_type):
    purchase = _find_purchase(data.get("id"))
    if purchase is None or purchase.status == PremiumPurchase.Status.COMPLETED:
        return

    transaction_status = data.get("status", "")
    if event_type == "transaction.canceled" or transaction_status == "canceled":
        purchase.status = PremiumPurchase.Status.CANCELED
        purchase.failure_reason = "Paddle 거래가 취소되었습니다."
    elif event_type in {"transaction.past_due", "transaction.payment_failed"} or transaction_status == "past_due":
        purchase.status = PremiumPurchase.Status.FAILED
        payments = data.get("payments") or []
        error_code = payments[0].get("error_code") if payments else None
        purchase.failure_reason = (
            f"Paddle 결제가 완료되지 않았습니다: {error_code}"
            if error_code
            else "Paddle 결제가 완료되지 않았습니다."
        )
    else:
        return
    purchase.save(update_fields=["status", "failure_reason", "modified_at"])


def _revoke_unused_entitlement(purchase, occurred_at):
    if purchase.revoked_at:
        return
    purchase.revoked_at = occurred_at
    if not purchase.entitlement_expires_at or purchase.user is None:
        return

    entitlement = (
        PremiumEntitlement.objects.select_for_update()
        .filter(user=purchase.user)
        .first()
    )
    if entitlement and entitlement.expires_at and entitlement.expires_at > occurred_at:
        unused_from = max(occurred_at, purchase.entitlement_started_at)
        unused_duration = max(
            timedelta(0),
            purchase.entitlement_expires_at - unused_from,
        )
        entitlement.expires_at = max(
            occurred_at,
            entitlement.expires_at - unused_duration,
        )
        entitlement.save(update_fields=["expires_at", "modified_at"])


def _process_adjustment(data, occurred_at):
    action = data.get("action")
    status = data.get("status")
    if action not in {"refund", "chargeback"} or status != "approved":
        return

    purchase = _find_purchase(data.get("transaction_id"))
    if purchase is None:
        return

    purchase.paddle_adjustment_id = data.get("id") or ""
    if data.get("type") != "full":
        purchase.status = PremiumPurchase.Status.PARTIALLY_REFUNDED
        purchase.save(
            update_fields=["status", "paddle_adjustment_id", "modified_at"]
        )
        return

    _revoke_unused_entitlement(purchase, occurred_at)
    purchase.status = (
        PremiumPurchase.Status.CHARGEBACK
        if action == "chargeback"
        else PremiumPurchase.Status.REFUNDED
    )
    purchase.save(
        update_fields=[
            "status",
            "paddle_adjustment_id",
            "revoked_at",
            "modified_at",
        ]
    )


@transaction.atomic
def process_webhook(payload):
    event_id = payload.get("event_id")
    event_type = payload.get("event_type")
    data = payload.get("data")
    if not event_id or not event_type or not isinstance(data, dict):
        raise PaddleWebhookValidationError("Paddle Webhook 필수 필드가 없습니다.")

    occurred_at = _event_time(payload)
    _, created = PaddleWebhookEvent.objects.get_or_create(
        event_id=event_id,
        defaults={
            "notification_id": payload.get("notification_id") or "",
            "event_type": event_type,
            "occurred_at": occurred_at,
            "payload": payload,
        },
    )
    if not created:
        return True

    if event_type == "transaction.completed":
        purchase = _find_purchase(data.get("id"))
        if purchase is not None:
            _grant_entitlement(purchase, data, occurred_at)
    elif event_type in {
        "transaction.canceled",
        "transaction.past_due",
        "transaction.payment_failed",
        "transaction.updated",
    }:
        _mark_transaction_state(data, event_type)
    elif event_type in {"adjustment.created", "adjustment.updated"}:
        _process_adjustment(data, occurred_at)

    return False
