"""마이페이지 결제 관리: 쿠폰과 PayApp 운세 이용권 현황."""
from django.utils import timezone

from fortune.models import FortunePurchase
from fortune.services.access import usable_purchase_status_q

COUPON_KEY_PREFIX = "coupon:"


def _remaining_days(purchase, today) -> int:
    """오늘을 포함해 남은 일수 (아직 시작 전이면 전체 일수)"""
    start = max(today, purchase.active_from)
    return max(0, (purchase.active_until - start).days + 1)


def _serialize(purchase, today) -> dict:
    is_coupon = (purchase.payment_key or "").startswith(COUPON_KEY_PREFIX)
    refund_request = getattr(purchase, "refund_request", None)
    return {
        "purchase_id": purchase.pk,
        "product_title": purchase.product_title,
        "duration_days": purchase.duration_days,
        "active_from": purchase.active_from,
        "active_until": purchase.active_until,
        "remaining_days": _remaining_days(purchase, today),
        "payment_method": "COUPON" if is_coupon else "PAYAPP",
        "can_request_refund": bool(
            not is_coupon
            and purchase.active_from <= today < purchase.active_until
            and refund_request is None
        ),
        "refund_status": refund_request.status if refund_request else None,
        # 기존 프론트 호환을 위해 필드명은 유지한다.
        "redeemed_at": (
            timezone.localtime(purchase.purchased_at) if purchase.purchased_at else None
        ),
    }


def build_my_passes(user, today) -> dict:
    passes = (
        FortunePurchase.objects.filter(
            user=user,
            active_from__isnull=False,
            active_until__isnull=False,
        )
        .filter(usable_purchase_status_q(today))
        .select_related("refund_request")
    )
    valid = list(passes.filter(active_until__gte=today).order_by("active_from", "pk"))

    current = next((p for p in valid if p.active_from <= today), None)
    upcoming = [p for p in valid if p.active_from > today]
    latest = passes.order_by("-purchased_at", "-pk").first()

    return {
        # 보유 코인 18/21: 지금 이용 중 + 예정 이용권을 합친 남은 일수 / 전체 일수
        "coins": {
            "remaining": sum(_remaining_days(p, today) for p in valid),
            "total": sum(p.duration_days for p in valid),
        },
        "current": _serialize(current, today) if current else None,
        "upcoming": [_serialize(p, today) for p in upcoming],
        "latest": _serialize(latest, today) if latest else None,
    }
