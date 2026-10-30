from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class FortuneProfile(models.Model):
    class CalendarType(models.TextChoices):
        SOLAR = "SOLAR", "양력"
        LUNAR_NORMAL = "LUNAR_NORMAL", "음력 평달"
        LUNAR_LEAP = "LUNAR_LEAP", "음력 윤달"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fortune_profile",
    )

    calendar_type = models.CharField(
        max_length=20,
        choices=CalendarType.choices,
    )

    birth_date = models.DateField()

    converted_solar_date = models.DateField(
        null=True,
        blank=True,
    )

    birth_time = models.TimeField(
        null=True,
        blank=True,
    )
    birth_time_unknown = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        birth_time_unknown=True,
                        birth_time__isnull=True,
                    )
                    | models.Q(
                        birth_time_unknown=False,
                        birth_time__isnull=False,
                    )
                ),
                name="valid_fortune_birth_time",
            )
        ]

    def clean(self):
        super().clean()

        if self.birth_time_unknown:
            self.birth_time = None
        elif self.birth_time is None:
            raise ValidationError({
                "birth_time": "태어난 시간을 입력하거나 모름을 선택해주세요."
            })

    def __str__(self):
        return f"{self.user_id} - {self.birth_date}"


class FortuneProduct(models.Model):
    class Duration(models.IntegerChoices):
        ONE_DAY = 1, "1일"
        SEVEN_DAYS = 7, "7일"
        FOURTEEN_DAYS = 14, "14일"
        TWENTY_ONE_DAYS = 21, "21일"

    product_code = models.CharField(
        max_length=30,
        unique=True,
    )
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.PositiveIntegerField()
    duration_days = models.PositiveSmallIntegerField(
        choices=Duration.choices,
    )
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"{self.title} ({self.duration_days}일)"

class FortunePurchase(models.Model):
    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", "결제 대기"
        PAID = "PAID", "결제 완료"
        FAILED = "FAILED", "결제 실패"
        CANCELED = "CANCELED", "결제 취소"
        REFUNDED = "REFUNDED", "환불"

    # 탈퇴해도 결제 기록은 환불·정산을 위해 남기고 사용자 연결만 끊는다
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fortune_purchases",
    )
    product = models.ForeignKey(
        FortuneProduct,
        on_delete=models.PROTECT,
        related_name="purchases",
    )

    product_title = models.CharField(max_length=100)
    duration_days = models.PositiveSmallIntegerField()
    amount = models.PositiveIntegerField()

    # 구매 이후 프로필이 바뀌어도 구매 당시 계산 기준을 보존합니다.
    calendar_type = models.CharField(
        max_length=20,
        choices=FortuneProfile.CalendarType.choices,
    )
    birth_date = models.DateField(null=True, blank=True)
    converted_solar_date = models.DateField(null=True, blank=True)
    birth_time = models.TimeField(null=True, blank=True)
    birth_time_unknown = models.BooleanField(default=False)

    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    payment_key = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )

    active_from = models.DateField(null=True, blank=True)
    active_until = models.DateField(null=True, blank=True)

    purchased_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["user", "payment_status", "active_until"],
                name="fortune_active_purchase_idx",
            )
        ]

    def __str__(self):
        return f"{self.user_id} - {self.product_title}"


class FortuneResult(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fortune_results",
    )

    target_date = models.DateField()

    title = models.CharField(max_length=100)
    image_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
    )

    luck_level = models.CharField(max_length=10, default="NORMAL")  # saju.LuckLevel
    character = models.CharField(max_length=20, blank=True, default="")  # characters.CHARACTERS
    summary = models.CharField(max_length=100, blank=True, default="")
    weather_condition = models.CharField(max_length=20, null=True, blank=True)  # WeatherCondition

    lucky_color = models.CharField(max_length=50)
    lucky_item = models.CharField(max_length=100)
    lucky_place = models.CharField(max_length=100)
    detail_text = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["target_date"]
        indexes = [
            models.Index(
                fields=["user", "target_date"],
                name="fortune_user_result_date_idx",
            )
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "target_date"],
                name="unique_fortune_result_per_user_date",
            )
        ]

    def __str__(self):
        return f"{self.target_date} - {self.title}"

class FortuneCoupon(models.Model):
    """굿즈(테루테루 카드)에 인쇄된 운세 이용권 코드. 한 코드는 한 번만 쓸 수 있다."""

    code = models.CharField(max_length=20, unique=True)
    product = models.ForeignKey(
        FortuneProduct,
        on_delete=models.PROTECT,
        related_name="coupons",
    )
    batch_label = models.CharField(max_length=50, blank=True)  # 발급 묶음 이름 (예: 10월 축제)
    expires_on = models.DateField(null=True, blank=True)  # 비어 있으면 무기한
    is_active = models.BooleanField(default=True)  # 분실·회수 시 운영진이 끈다

    redeemed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fortune_coupons",
    )
    redeemed_at = models.DateTimeField(null=True, blank=True)
    purchase = models.OneToOneField(
        FortunePurchase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coupon",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} ({self.product.product_code})"

class FortuneCouponAttempt(models.Model):
    """쿠폰 코드 입력 실패 횟수와 입력 제한 종료 시각 (사용자별)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fortune_coupon_attempt",
    )
    failed_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user_id} - 실패 {self.failed_count}회"