"""마이페이지 결제 관리: 내 운세 이용권(앱 결제 + 쿠폰 코드) 현황."""
from django.utils import timezone
from fortune.models import FortunePurchase

SOURCE_COUPON = "COUPON"
SOURCE_PAYMENT = "PAYMENT"


def _source(purchase) -> str:
    """쿠폰으로 받은 이용권은 payment_key가 'coupon:'으로 시작한다."""
    if (purchase.payment_key or "").startswith("coupon:"):
        return SOURCE_COUPON
    return SOURCE_PAYMENT


def _remaining_days(purchase, today) -> int:
    """오늘을 포함해 남은 일수 (아직 시작 전이면 전체 일수)"""
    start = max(today, purchase.active_from)
    return max(0, (purchase.active_until - start).days + 1)


def _serialize(purchase, today) -> dict:
    return {
        "purchase_id": purchase.pk,
        "product_title": purchase.product_title,
        "duration_days": purchase.duration_days,
        "source": _source(purchase),
        "amount": purchase.amount,
        "active_from": purchase.active_from,
        "active_until": purchase.active_until,
        "remaining_days": _remaining_days(purchase, today),
        "purchased_at": (
            timezone.localtime(purchase.purchased_at) if purchase.purchased_at else None
        ),
    }


def build_my_passes(user, today) -> dict:
    paid = FortunePurchase.objects.filter(
        user=user,
        payment_status=FortunePurchase.PaymentStatus.PAID,
        active_from__isnull=False,
        active_until__isnull=False,
    )
    valid = list(paid.filter(active_until__gte=today).order_by("active_from", "pk"))

    current = next((p for p in valid if p.active_from <= today), None)
    upcoming = [p for p in valid if p.active_from > today]
    latest = paid.order_by("-purchased_at", "-pk").first()

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