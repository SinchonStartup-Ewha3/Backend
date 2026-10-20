"""마이페이지 결제 관리: 내 운세 이용권 현황.

운세는 앱 안 결제 없이 굿즈 카드 코드로만 이용권을 지급하므로,
쿠폰 코드로 받은 이용권(payment_key가 'coupon:'으로 시작)만 보여준다.
기존 운세 결제 API(purchases/, confirm/)는 사용하지 않는 기능이다.
"""
from django.utils import timezone

from fortune.models import FortunePurchase

COUPON_KEY_PREFIX = "coupon:"


def _remaining_days(purchase, today) -> int:
    """오늘을 포함해 남은 일수 (아직 시작 전이면 전체 일수)"""
    start = max(today, purchase.active_from)
    return max(0, (purchase.active_until - start).days + 1)


def _serialize(purchase, today) -> dict:
    return {
        "purchase_id": purchase.pk,
        "product_title": purchase.product_title,
        "duration_days": purchase.duration_days,
        "active_from": purchase.active_from,
        "active_until": purchase.active_until,
        "remaining_days": _remaining_days(purchase, today),
        # 코드를 등록한 시각, 한국 시간(+09:00)
        "redeemed_at": (
            timezone.localtime(purchase.purchased_at) if purchase.purchased_at else None
        ),
    }


def build_my_passes(user, today) -> dict:
    passes = FortunePurchase.objects.filter(
        user=user,
        payment_status=FortunePurchase.PaymentStatus.PAID,
        payment_key__startswith=COUPON_KEY_PREFIX,
        active_from__isnull=False,
        active_until__isnull=False,
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