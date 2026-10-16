import json
import logging
import math

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    NotificationPreference,
    PremiumEntitlement,
    PremiumProfile,
    PremiumPurchase,
    PremiumRefundRequest,
)
from .permissions import HasActivePremium
from .serializers import (
    NotificationPreferenceSerializer,
    PremiumProfileSerializer,
    PremiumRefundRequestSerializer,
)
from .services.paddle import (
    PaddleAPIError,
    PaddleConfigurationError,
    PaddleWebhookSignatureError,
    create_transaction,
    validate_paddle_settings,
    verify_webhook_signature,
)
from .services.webhooks import PaddleWebhookValidationError, process_webhook


logger = logging.getLogger(__name__)


class PremiumProfileView(APIView):
    permission_classes = [IsAuthenticated, HasActivePremium]

    def get(self, request):
        profile = PremiumProfile.objects.filter(
            user=request.user,
        ).first()
        if profile is None:
            profile = PremiumProfile(user=request.user)

        return Response(PremiumProfileSerializer(profile).data)

    def put(self, request):
        return self.update_profile(request)

    def patch(self, request):
        return self.update_profile(request, partial=True)

    def update_profile(self, request, partial=False):
        profile, _ = PremiumProfile.objects.get_or_create(
            user=request.user,
        )
        serializer = PremiumProfileSerializer(
            profile,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)


class NotificationPreferenceView(APIView):
    permission_classes = [IsAuthenticated, HasActivePremium]

    def get(self, request):
        preference = NotificationPreference.objects.filter(
            user=request.user,
        ).first()
        if preference is None:
            preference = NotificationPreference(user=request.user)

        return Response(NotificationPreferenceSerializer(preference).data)

    def put(self, request):
        return self.update_preference(request)

    def patch(self, request):
        return self.update_preference(request, partial=True)

    def update_preference(self, request, partial=False):
        preference, _ = NotificationPreference.objects.get_or_create(
            user=request.user,
        )
        serializer = NotificationPreferenceSerializer(
            preference,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PremiumStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entitlement = PremiumEntitlement.objects.filter(user=request.user).first()
        now = timezone.now()
        is_premium = bool(entitlement and entitlement.is_active(now))
        remaining_seconds = 0
        if is_premium:
            remaining_seconds = max(
                0,
                math.ceil((entitlement.expires_at - now).total_seconds()),
            )
        return Response(
            {
                "isPremium": is_premium,
                "premiumStartedAt": entitlement.started_at if entitlement else None,
                "premiumExpiresAt": entitlement.expires_at if entitlement else None,
                "remainingSeconds": remaining_seconds,
            }
        )


class PremiumBillingView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        entitlement = PremiumEntitlement.objects.filter(
            user=request.user,
        ).first()
        is_premium = bool(entitlement and entitlement.is_active(now))
        remaining_seconds = 0
        if is_premium:
            remaining_seconds = max(
                0,
                math.ceil((entitlement.expires_at - now).total_seconds()),
            )

        latest_purchase = (
            PremiumPurchase.objects.filter(
                user=request.user,
                completed_at__isnull=False,
            )
            .order_by("-completed_at", "-pk")
            .first()
        )
        can_request_refund = (
            PremiumPurchase.objects.filter(
                user=request.user,
                status=PremiumPurchase.Status.COMPLETED,
                revoked_at__isnull=True,
                entitlement_expires_at__gt=now,
                refund_request__isnull=True,
            ).exists()
        )

        subscription_data = None
        if latest_purchase is not None:
            subscription_data = {
                "purchaseId": latest_purchase.pk,
                "productName": "맞춤형 행동 알림",
                "status": latest_purchase.status,
                "purchasedAt": latest_purchase.completed_at,
                "startedAt": entitlement.started_at if entitlement else None,
                "expiresAt": entitlement.expires_at if entitlement else None,
                "isActive": is_premium,
                "remainingSeconds": remaining_seconds,
                "canRequestRefund": can_request_refund,
            }

        return Response({"subscription": subscription_data})


class PremiumCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            validate_paddle_settings()
        except PaddleConfigurationError as exc:
            return Response(
                {"detail": str(exc), "code": "PADDLE_NOT_CONFIGURED"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        purchase = PremiumPurchase.objects.create(
            user=request.user,
            paddle_price_id=settings.PADDLE_PRICE_ID,
            amount=settings.PADDLE_PREMIUM_AMOUNT,
            currency_code=settings.PADDLE_PREMIUM_CURRENCY,
        )
        try:
            paddle_transaction = create_transaction(purchase=purchase)
        except (PaddleAPIError, PaddleConfigurationError) as exc:
            purchase.status = PremiumPurchase.Status.FAILED
            purchase.failure_reason = str(exc)[:255]
            purchase.save(update_fields=["status", "failure_reason", "modified_at"])
            return Response(
                {"detail": str(exc), "code": "PADDLE_TRANSACTION_FAILED"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        purchase.paddle_transaction_id = paddle_transaction["id"]
        purchase.save(update_fields=["paddle_transaction_id", "modified_at"])
        checkout = paddle_transaction.get("checkout") or {}
        return Response(
            {
                "purchaseId": purchase.pk,
                "transactionId": purchase.paddle_transaction_id,
                "checkoutUrl": checkout.get("url"),
                "status": purchase.status,
            },
            status=status.HTTP_201_CREATED,
        )


class PremiumRefundRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        refund_request = (
            PremiumRefundRequest.objects.filter(user=request.user)
            .select_related("purchase")
            .first()
        )
        if refund_request is None:
            return Response(
                {
                    "detail": "환불 요청 내역이 없습니다.",
                    "code": "REFUND_REQUEST_NOT_FOUND",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(PremiumRefundRequestSerializer(refund_request).data)

    def post(self, request):
        now = timezone.now()
        purchase = (
            PremiumPurchase.objects.filter(
                user=request.user,
                status=PremiumPurchase.Status.COMPLETED,
                revoked_at__isnull=True,
                entitlement_expires_at__gt=now,
            )
            .order_by("-completed_at", "-pk")
            .first()
        )
        if purchase is None:
            return self.no_refundable_purchase_response()

        existing_request = PremiumRefundRequest.objects.filter(
            purchase=purchase,
        ).first()
        if existing_request is not None:
            return self.duplicate_request_response(existing_request)

        serializer = PremiumRefundRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                purchase = PremiumPurchase.objects.select_for_update().get(
                    pk=purchase.pk,
                    user=request.user,
                    status=PremiumPurchase.Status.COMPLETED,
                    revoked_at__isnull=True,
                    entitlement_expires_at__gt=timezone.now(),
                )
                refund_request = serializer.save(
                    user=request.user,
                    purchase=purchase,
                )
        except PremiumPurchase.DoesNotExist:
            return self.no_refundable_purchase_response()
        except IntegrityError:
            existing_request = PremiumRefundRequest.objects.get(
                purchase=purchase,
            )
            return self.duplicate_request_response(existing_request)

        return Response(
            PremiumRefundRequestSerializer(refund_request).data,
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def no_refundable_purchase_response():
        return Response(
            {
                "detail": "환불을 요청할 수 있는 프리미엄 결제 내역이 없습니다.",
                "code": "NO_REFUNDABLE_PURCHASE",
            },
            status=status.HTTP_409_CONFLICT,
        )

    @staticmethod
    def duplicate_request_response(refund_request):
        return Response(
            {
                "detail": "이미 환불을 요청한 결제입니다.",
                "code": "REFUND_REQUEST_ALREADY_EXISTS",
                "refundRequest": PremiumRefundRequestSerializer(
                    refund_request
                ).data,
            },
            status=status.HTTP_409_CONFLICT,
        )


class PaddleWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        raw_body = request.body
        try:
            verify_webhook_signature(
                raw_body,
                request.headers.get("Paddle-Signature", ""),
            )
        except (PaddleWebhookSignatureError, PaddleConfigurationError) as exc:
            return Response(
                {"detail": str(exc), "code": "INVALID_PADDLE_SIGNATURE"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            payload = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Response(
                {"detail": "Webhook JSON이 올바르지 않습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            duplicate = process_webhook(payload)
        except PaddleWebhookValidationError as exc:
            return Response(
                {"detail": str(exc), "code": "INVALID_PADDLE_EVENT"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception(
                "Unexpected error while processing Paddle webhook.",
                extra={
                    "paddle_event_id": payload.get("event_id"),
                    "paddle_event_type": payload.get("event_type"),
                },
            )
            raise
        return Response({"ok": True, "duplicate": duplicate})
