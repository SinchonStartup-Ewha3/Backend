import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class PremiumEntitlement(models.Model):
    """Webhook으로 확정된 사용자의 현재 프리미엄 이용 기간."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="premium_entitlement",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    def is_active(self, at=None):
        at = at or timezone.now()
        return bool(
            self.started_at
            and self.expires_at
            and self.started_at <= at < self.expires_at
        )

    def __str__(self):
        return f"{self.user_id}: {self.started_at} ~ {self.expires_at}"


class PremiumPurchase(models.Model):
    """WEE Premium Paddle 거래와 권한 지급/회수 이력."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "결제 대기"
        COMPLETED = "COMPLETED", "결제 완료"
        FAILED = "FAILED", "결제 실패"
        CANCELED = "CANCELED", "결제 취소"
        PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED", "부분 환불"
        REFUNDED = "REFUNDED", "전액 환불"
        CHARGEBACK = "CHARGEBACK", "차지백"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="premium_purchases",
    )
    paddle_transaction_id = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
    )
    paddle_customer_id = models.CharField(max_length=50, blank=True)
    paddle_product_id = models.CharField(max_length=50, blank=True)
    paddle_price_id = models.CharField(max_length=50)
    paddle_adjustment_id = models.CharField(max_length=50, blank=True)
    amount = models.PositiveIntegerField()
    currency_code = models.CharField(max_length=3)
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING,
    )
    entitlement_started_at = models.DateTimeField(null=True, blank=True)
    entitlement_expires_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["user", "status", "created_at"],
                name="premium_purchase_user_idx",
            ),
        ]

    def __str__(self):
        return f"{self.user_id} - {self.paddle_transaction_id or self.pk}"


class BankTransferRequest(models.Model):
    """사용자가 직접 계좌이체 후 등록한 입금 확인 요청."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "입금 확인 중"
        APPROVED = "APPROVED", "입금 승인"
        REJECTED = "REJECTED", "입금 거절"
        CANCELED = "CANCELED", "사용자 취소"
        REFUNDED = "REFUNDED", "환불 완료"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bank_transfer_requests",
    )
    depositor_name = models.CharField(max_length=30)
    amount = models.PositiveIntegerField(default=2500)
    currency_code = models.CharField(max_length=3, default="KRW")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    entitlement_started_at = models.DateTimeField(null=True, blank=True)
    entitlement_expires_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_bank_transfer_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status="PENDING"),
                name="uniq_pending_bank_user",
            ),
        ]

    def __str__(self):
        return f"{self.user.nickname} - {self.depositor_name} - {self.status}"


class PayAppPayment(models.Model):
    """PayApp 일회성 결제 요청과 Premium 권한 지급 이력."""

    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "결제 요청"
        WAITING = "WAITING", "결제 대기"
        COMPLETED = "COMPLETED", "결제 완료"
        FAILED = "FAILED", "결제 요청 실패"
        REQUEST_CANCELED = "REQUEST_CANCELED", "결제 요청 취소"
        APPROVAL_CANCELED = "APPROVAL_CANCELED", "결제 승인 취소"
        PARTIALLY_CANCELED = "PARTIALLY_CANCELED", "부분 취소"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payapp_payments",
    )
    order_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    mul_no = models.CharField(max_length=64, unique=True, null=True, blank=True)
    pay_url = models.URLField(max_length=500, blank=True)
    product_name = models.CharField(max_length=100)
    amount = models.PositiveIntegerField()
    currency_code = models.CharField(max_length=3, default="KRW")
    buyer_phone_masked = models.CharField(max_length=20, blank=True)
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.REQUESTED,
    )
    provider_state = models.CharField(max_length=10, blank=True)
    entitlement_started_at = models.DateTimeField(null=True, blank=True)
    entitlement_expires_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    provider_canceled_at = models.DateTimeField(null=True, blank=True)
    refund_confirmed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    admin_note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["user", "status", "created_at"],
                name="payapp_payment_user_idx",
            ),
        ]

    def __str__(self):
        return f"{self.user_id} - {self.mul_no or self.order_token}"


class PayAppFeedbackEvent(models.Model):
    """민감정보를 제외한 PayApp 통보 처리 및 멱등성 기록."""

    event_key = models.CharField(max_length=64, primary_key=True)
    payment = models.ForeignKey(
        PayAppPayment,
        on_delete=models.PROTECT,
        related_name="feedback_events",
    )
    mul_no = models.CharField(max_length=64)
    pay_state = models.CharField(max_length=10)
    responsedate = models.CharField(max_length=14)
    price = models.PositiveIntegerField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.mul_no}: {self.pay_state}"


class PremiumRefundRequest(models.Model):
    """사용자가 접수하고 운영진이 결제수단별로 처리하는 환불 요청."""

    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "환불 요청"
        PROCESSING = "PROCESSING", "환불 처리 중"
        COMPLETED = "COMPLETED", "환불 완료"
        REJECTED = "REJECTED", "환불 거절"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="premium_refund_requests",
    )
    purchase = models.OneToOneField(
        PremiumPurchase,
        on_delete=models.PROTECT,
        related_name="refund_request",
        null=True,
        blank=True,
    )
    bank_transfer_request = models.OneToOneField(
        BankTransferRequest,
        on_delete=models.PROTECT,
        related_name="refund_request",
        null=True,
        blank=True,
    )
    payapp_payment = models.OneToOneField(
        PayAppPayment,
        on_delete=models.PROTECT,
        related_name="refund_request",
        null=True,
        blank=True,
    )
    reason = models.CharField(max_length=500)
    requested_amount = models.PositiveIntegerField()
    currency_code = models.CharField(max_length=3)
    remaining_seconds = models.PositiveBigIntegerField()
    paddle_adjustment_id = models.CharField(max_length=50, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.REQUESTED,
    )
    rejection_reason = models.CharField(max_length=255, blank=True)
    access_suspended_at = models.DateTimeField(null=True, blank=True)
    access_restored_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "status", "created_at"],
                name="premium_refund_user_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(
                        purchase__isnull=False,
                        bank_transfer_request__isnull=True,
                        payapp_payment__isnull=True,
                    )
                    | Q(
                        purchase__isnull=True,
                        bank_transfer_request__isnull=False,
                        payapp_payment__isnull=True,
                    )
                    | Q(
                        purchase__isnull=True,
                        bank_transfer_request__isnull=True,
                        payapp_payment__isnull=False,
                    )
                ),
                name="refund_exactly_one_payment_source",
            ),
        ]

    def __str__(self):
        payment_id = (
            self.purchase_id
            or self.bank_transfer_request_id
            or self.payapp_payment_id
        )
        return f"{self.user_id} - {payment_id} - {self.status}"


class PaddleWebhookEvent(models.Model):
    """event_id를 PK로 사용해 Paddle의 at-least-once 전송을 멱등 처리한다."""

    event_id = models.CharField(max_length=50, primary_key=True)
    notification_id = models.CharField(max_length=50, blank=True)
    event_type = models.CharField(max_length=100)
    occurred_at = models.DateTimeField()
    payload = models.JSONField()
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"{self.event_type}: {self.event_id}"


class PremiumProfile(models.Model):
    """프리미엄 맞춤 알림에 필요한 사용자 성향을 저장한다."""

    class ColdSensitivity(models.TextChoices):
        VERY_SENSITIVE = "VERY_SENSITIVE", "추위를 많이 타요"
        NORMAL = "NORMAL", "보통이에요"
        HEAT_SENSITIVE = "HEAT_SENSITIVE", "더위를 더 잘 느껴요"
        UNKNOWN = "UNKNOWN", "잘 모르겠어요"

    class ExercisePreference(models.TextChoices):
        MORNING = "MORNING", "아침에 자주 해요"
        EVENING = "EVENING", "저녁에 자주 해요"
        GOOD_WEATHER_ONLY = "GOOD_WEATHER_ONLY", "날씨가 좋을 때만 해요"
        FLEXIBLE = "FLEXIBLE", "정해진 시간은 없어요"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="premium_profile",
    )

    cold_sensitivity = models.CharField(
        max_length=30,
        choices=ColdSensitivity.choices,
        default=ColdSensitivity.UNKNOWN,
    )

    exercise_preference = models.CharField(
        max_length=30,
        choices=ExercisePreference.choices,
        default=ExercisePreference.FLEXIBLE,
    )

    laundry_rain_alert = models.BooleanField(default=False)
    laundry_humidity_alert = models.BooleanField(default=False)
    laundry_indoor_tip = models.BooleanField(default=False)

    survey_completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.nickname}의 프리미엄 설정"


class NotificationPreference(models.Model):
    """맞춤 알림 종류별 수신 여부를 저장한다."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preference",
    )
    outerwear_enabled = models.BooleanField(default=False)
    exercise_enabled = models.BooleanField(default=False)
    laundry_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.nickname}의 알림 설정"
