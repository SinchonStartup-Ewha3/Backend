"""굿즈 카드 코드로 운세 이용권을 지급한다."""
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from fortune.models import (
    FortuneCoupon,
    FortuneCouponAttempt,
    FortuneProfile,
    FortunePurchase,
)

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


# 이 코드들은 "코드를 맞히려는 시도"로 보고 실패 횟수에 넣는다.
COUNTED_ERRORS = {"COUPON_INVALID", "COUPON_ALREADY_USED", "COUPON_EXPIRED"}


def _too_many_attempts_error():
    return CouponError(
        "COUPON_TOO_MANY_ATTEMPTS",
        "코드를 여러 번 잘못 입력했어요. 1시간 뒤에 다시 시도해주세요.",
        429,
    )


def redeem_coupon(user, raw_code: str) -> FortunePurchase:
    """코드를 확인하고 이용권을 지급한다.

    - 사용자 행을 먼저 잠가서, 같은 사용자의 등록 요청은 한 번에 하나씩 처리한다.
      (서로 다른 쿠폰 두 개를 동시에 넣어도 이용 기간이 겹치지 않는다)
    - 실패 횟수와 입력 제한 시각은 DB에 저장해 Gunicorn worker가 여러 개여도 정확하다.
    """
    code = normalize_code(raw_code)
    error = None

    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=user.pk)
        attempt, _ = FortuneCouponAttempt.objects.get_or_create(user=user)
        now = timezone.now()

        if attempt.locked_until and attempt.locked_until > now:
            error = _too_many_attempts_error()
        else:
            profile = FortuneProfile.objects.filter(user=user).first()
            if profile is None:
                error = CouponError(
                    "FORTUNE_PROFILE_REQUIRED",
                    "생년월일 정보를 먼저 입력해주세요.",
                    409,
                )
            else:
                try:
                    purchase = _redeem(user, code, profile)
                except CouponError as coupon_error:
                    error = coupon_error
                else:
                    # 정상 등록하면 실패 기록을 초기화한다.
                    attempt.failed_count = 0
                    attempt.locked_until = None
                    attempt.save(update_fields=["failed_count", "locked_until", "modified_at"])
                    return purchase

        if error.code in COUNTED_ERRORS:
            attempt.failed_count += 1
            if attempt.failed_count >= MAX_FAILED_ATTEMPTS:
                # 잠금을 걸고 횟수는 0으로 돌려, 잠금이 풀리면 다시 5번 시도할 수 있다.
                attempt.locked_until = now + timedelta(seconds=LOCK_SECONDS)
                attempt.failed_count = 0
            attempt.save(update_fields=["failed_count", "locked_until", "modified_at"])

    # 실패 기록은 저장(커밋)한 뒤에 오류를 돌려준다.
    raise error


def _redeem(user, code, profile):
    """redeem_coupon의 트랜잭션 안에서만 호출한다. 검사를 모두 통과한 뒤에만 저장한다."""
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