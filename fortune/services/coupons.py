"""굿즈 카드 코드로 운세 이용권을 지급한다."""
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from fortune.models import FortuneCoupon, FortuneProfile, FortunePurchase

# 헷갈리는 글자(0, O, 1, I, L)를 뺀 31자
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

MAX_FAILED_ATTEMPTS = 5
LOCK_SECONDS = 60 * 60


class CouponError(Exception):
    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def normalize_code(raw: str) -> str:
    """공백·하이픈을 지우고 대문자로 바꾼다 (k7-qm → K7QM)"""
    return re.sub(r"[\s-]", "", raw or "").upper()


def generate_code(length: int | None = None) -> str:
    length = length or settings.FORTUNE_COUPON_CODE_LENGTH
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def _fail_key(user) -> str:
    return f"fortune-coupon-fail:{user.pk}"


def _check_not_locked(user):
    if cache.get(_fail_key(user), 0) >= MAX_FAILED_ATTEMPTS:
        raise CouponError(
            "COUPON_TOO_MANY_ATTEMPTS",
            "코드를 여러 번 잘못 입력했어요. 1시간 뒤에 다시 시도해주세요.",
            429,
        )


def _record_failure(user):
    key = _fail_key(user)
    try:
        cache.incr(key)
    except ValueError:  # 키가 없으면 새로 만든다
        cache.set(key, 1, LOCK_SECONDS)


def _next_start_date(user, today):
    """이미 이용 중인 이용권이 있으면 그 다음 날부터 시작한다."""
    latest = (
        FortunePurchase.objects.select_for_update()
        .filter(
            user=user,
            payment_status=FortunePurchase.PaymentStatus.PAID,
            active_until__gte=today,
        )
        .order_by("-active_until")
        .first()
    )
    if latest is None:
        return today
    if settings.FORTUNE_COUPON_STACK_POLICY == "BLOCK":
        raise CouponError(
            "ACTIVE_PURCHASE_EXISTS",
            "이미 이용 중인 운세 이용권이 있어요.",
            409,
        )
    return latest.active_until + timedelta(days=1)


def redeem_coupon(user, raw_code: str) -> FortunePurchase:
    _check_not_locked(user)
    code = normalize_code(raw_code)

    profile = FortuneProfile.objects.filter(user=user).first()
    if profile is None:
        raise CouponError(
            "FORTUNE_PROFILE_REQUIRED",
            "생년월일 정보를 먼저 입력해주세요.",
            409,
        )

    try:
        return _redeem(user, code, profile)
    except CouponError as error:
        if error.code in {"COUPON_INVALID", "COUPON_ALREADY_USED", "COUPON_EXPIRED"}:
            _record_failure(user)
        raise


@transaction.atomic
def _redeem(user, code, profile):
    today = timezone.localdate()
    coupon = (
        FortuneCoupon.objects.select_for_update()
        .select_related("product")
        .filter(code=code, is_active=True)
        .first()
    )
    if coupon is None:
        raise CouponError("COUPON_INVALID", "올바른 코드가 아니에요.", 400)
    if coupon.redeemed_at is not None:
        raise CouponError("COUPON_ALREADY_USED", "이미 사용된 코드예요.", 409)
    if coupon.expires_on and coupon.expires_on < today:
        raise CouponError("COUPON_EXPIRED", "사용 기간이 지난 코드예요.", 400)

    start = _next_start_date(user, today)
    product = coupon.product
    now = timezone.now()

    # 굿즈 구매는 앱 밖에서 끝났으므로 앱 안 결제 금액은 0원으로 기록한다.
    purchase = FortunePurchase.objects.create(
        user=user,
        product=product,
        product_title=product.title,
        duration_days=product.duration_days,
        amount=0,
        calendar_type=profile.calendar_type,
        birth_date=profile.birth_date,
        converted_solar_date=profile.converted_solar_date,
        birth_time=profile.birth_time,
        birth_time_unknown=profile.birth_time_unknown,
        payment_status=FortunePurchase.PaymentStatus.PAID,
        payment_key=f"coupon:{coupon.code}",
        active_from=start,
        active_until=start + timedelta(days=product.duration_days - 1),
        purchased_at=now,
    )

    coupon.redeemed_by = user
    coupon.redeemed_at = now
    coupon.purchase = purchase
    coupon.save(update_fields=["redeemed_by", "redeemed_at", "purchase"])
    return purchase