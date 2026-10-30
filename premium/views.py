import json
import logging
import math

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    BankTransferRequest,
    NotificationPreference,
    PayAppPayment,
    PremiumEntitlement,
    PremiumProfile,
    PremiumPurchase,
    PremiumRefundRequest,
)
from .permissions import CanAccessPremiumSurvey, HasActivePremium
from .serializers import (
    BankTransferRequestSerializer,
    NotificationPreferenceSerializer,
    PayAppCheckoutSerializer,
    PremiumProfileSerializer,
    PremiumRefundRequestSerializer,
)
from .services.paddle import (
    PaddleConfigurationError,
    PaddleWebhookSignatureError,
    verify_webhook_signature,
)
from .services.refunds import (
    RefundCalculationError,
    calculate_prorated_refund,
    suspend_refund_access,
)
from .services.payapp import (
    PayAppAPIError,
    PayAppConfigurationError,
    PayAppFeedbackValidationError,
    create_payment_request,
    mask_phone,
    process_feedback,
    validate_payapp_settings,
)
from .services.webhooks import PaddleWebhookValidationError, process_webhook


logger = logging.getLogger(__name__)


class PremiumProfileView(APIView):
    permission_classes = [IsAuthenticated, CanAccessPremiumSurvey]

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

        latest_bank_transfer = (
            BankTransferRequest.objects.filter(user=request.user)
            .order_by("-created_at")
            .first()
        )
        bank_transfer_status = (
            latest_bank_transfer.status if latest_bank_transfer else None
        )
        active_bank_transfer = is_premium and (
            BankTransferRequest.objects.filter(
                user=request.user,
                status=BankTransferRequest.Status.APPROVED,
                entitlement_started_at__lte=now,
                entitlement_expires_at__gt=now,
            )
            .exclude(
                refund_request__status__in=[
                    PremiumRefundRequest.Status.REQUESTED,
                    PremiumRefundRequest.Status.PROCESSING,
                    PremiumRefundRequest.Status.COMPLETED,
                ]
            )
            .exists()
        )
        active_payapp_payment = (
            PayAppPayment.objects.filter(
                user=request.user,
                status=PayAppPayment.Status.COMPLETED,
                refund_confirmed_at__isnull=True,
                entitlement_started_at__lte=now,
                entitlement_expires_at__gt=now,
            )
            .exclude(
                refund_request__status__in=[
                    PremiumRefundRequest.Status.REQUESTED,
                    PremiumRefundRequest.Status.PROCESSING,
                    PremiumRefundRequest.Status.COMPLETED,
                ]
            )
            .exists()
        )
        active_paddle_purchase = PremiumPurchase.objects.filter(
            user=request.user,
            status__in=[
                PremiumPurchase.Status.COMPLETED,
                PremiumPurchase.Status.PARTIALLY_REFUNDED,
            ],
            revoked_at__isnull=True,
            entitlement_started_at__lte=now,
            entitlement_expires_at__gt=now,
        ).exists()
        if active_bank_transfer:
            payment_method = "BANK_TRANSFER"
        elif active_payapp_payment:
            payment_method = "PAYAPP"
        elif active_paddle_purchase:
            payment_method = "PADDLE"
        elif is_premium:
            payment_method = "MANUAL"
        else:
            payment_method = None

        return Response(
            {
                "isPremium": is_premium,
                "canCompleteSurvey": (
                    is_premium
                    or bank_transfer_status == BankTransferRequest.Status.PENDING
                ),
                "bankTransferStatus": bank_transfer_status,
                "paymentMethod": payment_method,
                "premiumStartedAt": entitlement.started_at if entitlement else None,
                "premiumExpiresAt": entitlement.expires_at if entitlement else None,
                "remainingSeconds": remaining_seconds,
            }
        )


class BankTransferRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        transfer_request = (
            BankTransferRequest.objects.filter(user=request.user)
            .order_by("-created_at")
            .first()
        )
        if transfer_request is None:
            return Response(
                {
                    "detail": "계좌이체 요청이 없습니다.",
                    "code": "BANK_TRANSFER_REQUEST_NOT_FOUND",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(BankTransferRequestSerializer(transfer_request).data)

    def post(self, request):
        now = timezone.now()
        entitlement = PremiumEntitlement.objects.filter(user=request.user).first()
        if entitlement and entitlement.is_active(now):
            return Response(
                {
                    "detail": "이미 프리미엄을 이용 중입니다.",
                    "code": "PREMIUM_ALREADY_ACTIVE",
                },
                status=status.HTTP_409_CONFLICT,
            )

        existing_request = BankTransferRequest.objects.filter(
            user=request.user,
            status=BankTransferRequest.Status.PENDING,
        ).first()
        if existing_request is not None:
            return Response(
                BankTransferRequestSerializer(existing_request).data,
                status=status.HTTP_200_OK,
            )

        serializer = BankTransferRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            transfer_request = serializer.save(
                user=request.user,
                amount=settings.PADDLE_PREMIUM_AMOUNT,
                currency_code=settings.PADDLE_PREMIUM_CURRENCY,
            )
        except IntegrityError:
            transfer_request = BankTransferRequest.objects.get(
                user=request.user,
                status=BankTransferRequest.Status.PENDING,
            )
            return Response(
                BankTransferRequestSerializer(transfer_request).data,
                status=status.HTTP_200_OK,
            )

        return Response(
            BankTransferRequestSerializer(transfer_request).data,
            status=status.HTTP_201_CREATED,
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
        latest_bank_transfer = (
            BankTransferRequest.objects.filter(
                user=request.user,
                reviewed_at__isnull=False,
            )
            .order_by("-reviewed_at", "-pk")
            .first()
        )
        latest_payapp_payment = (
            PayAppPayment.objects.filter(
                user=request.user,
                completed_at__isnull=False,
            )
            .order_by("-completed_at", "-pk")
            .first()
        )
        paddle_can_refund = (
            PremiumPurchase.objects.filter(
                user=request.user,
                status=PremiumPurchase.Status.COMPLETED,
                revoked_at__isnull=True,
                entitlement_expires_at__gt=now,
                refund_request__isnull=True,
            ).exists()
        )
        bank_can_refund = BankTransferRequest.objects.filter(
            user=request.user,
            status=BankTransferRequest.Status.APPROVED,
            entitlement_expires_at__gt=now,
            refund_request__isnull=True,
        ).exists()
        payapp_can_refund = PayAppPayment.objects.filter(
            pk=latest_payapp_payment.pk if latest_payapp_payment else None,
            status=PayAppPayment.Status.COMPLETED,
            refund_confirmed_at__isnull=True,
            entitlement_expires_at__gt=now,
            refund_request__isnull=True,
        ).exists()
        bank_refund_blocks_access = bool(
            latest_bank_transfer
            and PremiumRefundRequest.objects.filter(
                bank_transfer_request=latest_bank_transfer,
                status__in=[
                    PremiumRefundRequest.Status.REQUESTED,
                    PremiumRefundRequest.Status.PROCESSING,
                    PremiumRefundRequest.Status.COMPLETED,
                ],
            ).exists()
        )
        payapp_refund_blocks_access = bool(
            latest_payapp_payment
            and PremiumRefundRequest.objects.filter(
                payapp_payment=latest_payapp_payment,
                status__in=[
                    PremiumRefundRequest.Status.REQUESTED,
                    PremiumRefundRequest.Status.PROCESSING,
                    PremiumRefundRequest.Status.COMPLETED,
                ],
            ).exists()
        )

        subscription_data = None
        use_payapp = bool(
            latest_payapp_payment
            and (
                latest_purchase is None
                or latest_payapp_payment.completed_at >= latest_purchase.completed_at
            )
            and (
                latest_bank_transfer is None
                or latest_payapp_payment.completed_at >= latest_bank_transfer.reviewed_at
            )
        )
        use_bank_transfer = bool(
            latest_bank_transfer
            and (
                latest_purchase is None
                or latest_bank_transfer.reviewed_at >= latest_purchase.completed_at
            )
            and (
                latest_payapp_payment is None
                or latest_bank_transfer.reviewed_at
                >= latest_payapp_payment.completed_at
            )
        )
        if use_payapp:
            payapp_is_active = bool(
                is_premium
                and not payapp_refund_blocks_access
                and latest_payapp_payment.entitlement_started_at
                and latest_payapp_payment.entitlement_expires_at
                and latest_payapp_payment.entitlement_started_at <= now
                < latest_payapp_payment.entitlement_expires_at
            )
            subscription_data = {
                "purchaseId": None,
                "bankTransferRequestId": None,
                "payAppPaymentId": latest_payapp_payment.pk,
                "paymentMethod": "PAYAPP",
                "productName": latest_payapp_payment.product_name,
                "status": latest_payapp_payment.status,
                "purchasedAt": latest_payapp_payment.completed_at,
                "startedAt": latest_payapp_payment.entitlement_started_at,
                "expiresAt": latest_payapp_payment.entitlement_expires_at,
                "isActive": payapp_is_active,
                "remainingSeconds": remaining_seconds if payapp_is_active else 0,
                "canRequestRefund": payapp_can_refund,
            }
        elif use_bank_transfer:
            bank_is_active = bool(
                is_premium
                and not bank_refund_blocks_access
                and latest_bank_transfer.status
                == BankTransferRequest.Status.APPROVED
                and latest_bank_transfer.entitlement_started_at
                and latest_bank_transfer.entitlement_expires_at
                and latest_bank_transfer.entitlement_started_at <= now
                < latest_bank_transfer.entitlement_expires_at
            )
            subscription_data = {
                "purchaseId": None,
                "bankTransferRequestId": latest_bank_transfer.pk,
                "paymentMethod": "BANK_TRANSFER",
                "productName": "맞춤형 행동 알림",
                "status": latest_bank_transfer.status,
                "purchasedAt": latest_bank_transfer.reviewed_at,
                "startedAt": latest_bank_transfer.entitlement_started_at,
                "expiresAt": latest_bank_transfer.entitlement_expires_at,
                "isActive": bank_is_active,
                "remainingSeconds": remaining_seconds if bank_is_active else 0,
                "canRequestRefund": bank_can_refund,
            }
        elif latest_purchase is not None:
            subscription_data = {
                "purchaseId": latest_purchase.pk,
                "bankTransferRequestId": None,
                "paymentMethod": "PADDLE",
                "productName": "맞춤형 행동 알림",
                "status": latest_purchase.status,
                "purchasedAt": latest_purchase.completed_at,
                "startedAt": entitlement.started_at if entitlement else None,
                "expiresAt": entitlement.expires_at if entitlement else None,
                "isActive": is_premium,
                "remainingSeconds": remaining_seconds,
                "canRequestRefund": paddle_can_refund,
            }

        return Response({"subscription": subscription_data})


class PremiumCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response(
            {
                "detail": "Paddle 결제는 더 이상 지원하지 않습니다.",
                "code": "PADDLE_DISABLED",
            },
            status=status.HTTP_410_GONE,
        )


class PayAppCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PayAppCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            validate_payapp_settings()
        except PayAppConfigurationError as exc:
            return Response(
                {"detail": str(exc), "code": "PAYAPP_NOT_CONFIGURED"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        recvphone = serializer.validated_data["recvphone"]
        payment = PayAppPayment.objects.create(
            user=request.user,
            product_name=settings.PAYAPP_PRODUCT_NAME,
            amount=settings.PAYAPP_PREMIUM_AMOUNT,
            currency_code=settings.PAYAPP_PREMIUM_CURRENCY,
            buyer_phone_masked=mask_phone(recvphone),
        )
        try:
            payapp_response = create_payment_request(
                payment=payment,
                recvphone=recvphone,
            )
        except (PayAppAPIError, PayAppConfigurationError) as exc:
            payment.status = PayAppPayment.Status.FAILED
            payment.failure_reason = str(exc)[:255]
            payment.save(update_fields=["status", "failure_reason", "modified_at"])
            return Response(
                {"detail": str(exc), "code": "PAYAPP_PAYMENT_REQUEST_FAILED"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        payment.mul_no = str(payapp_response["mul_no"])
        payment.pay_url = payapp_response["payurl"]
        try:
            payment.save(update_fields=["mul_no", "pay_url", "modified_at"])
        except IntegrityError:
            payment.mul_no = None
            payment.pay_url = ""
            payment.status = PayAppPayment.Status.FAILED
            payment.failure_reason = "이미 처리된 PayApp 결제요청번호가 반환되었습니다."
            payment.save(
                update_fields=[
                    "mul_no",
                    "pay_url",
                    "status",
                    "failure_reason",
                    "modified_at",
                ]
            )
            return Response(
                {
                    "detail": payment.failure_reason,
                    "code": "PAYAPP_DUPLICATE_MUL_NO",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(
            {
                "paymentId": payment.pk,
                "mulNo": payment.mul_no,
                "paymentUrl": payment.pay_url,
                "status": payment.status,
            },
            status=status.HTTP_201_CREATED,
        )


class PremiumRefundRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        refund_request = (
            PremiumRefundRequest.objects.filter(user=request.user)
            .select_related("purchase", "bank_transfer_request", "payapp_payment")
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
        payapp_payment = (
            PayAppPayment.objects.filter(
                user=request.user,
                status=PayAppPayment.Status.COMPLETED,
                refund_confirmed_at__isnull=True,
                entitlement_expires_at__gt=now,
            )
            .order_by("-completed_at", "-pk")
            .first()
        )
        bank_transfer_request = (
            BankTransferRequest.objects.filter(
                user=request.user,
                status=BankTransferRequest.Status.APPROVED,
                entitlement_expires_at__gt=now,
            )
            .order_by("-reviewed_at", "-pk")
            .first()
        )
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
        if (
            payapp_payment is None
            and bank_transfer_request is None
            and purchase is None
        ):
            return self.no_refundable_purchase_response()

        if payapp_payment is not None:
            source_filter = {"payapp_payment": payapp_payment}
        elif bank_transfer_request is not None:
            source_filter = {"bank_transfer_request": bank_transfer_request}
        else:
            source_filter = {"purchase": purchase}
        existing_request = PremiumRefundRequest.objects.filter(**source_filter).first()
        if existing_request is not None:
            return self.duplicate_request_response(existing_request)

        serializer = PremiumRefundRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                if payapp_payment is not None:
                    payapp_payment = PayAppPayment.objects.select_for_update().get(
                        pk=payapp_payment.pk,
                        user=request.user,
                        status=PayAppPayment.Status.COMPLETED,
                        refund_confirmed_at__isnull=True,
                        entitlement_expires_at__gt=timezone.now(),
                    )
                    prorated_refund = calculate_prorated_refund(
                        payapp_payment,
                        requested_at=now,
                    )
                    refund_request = serializer.save(
                        user=request.user,
                        payapp_payment=payapp_payment,
                        requested_amount=prorated_refund.amount,
                        currency_code=payapp_payment.currency_code,
                        remaining_seconds=prorated_refund.remaining_seconds,
                    )
                elif bank_transfer_request is not None:
                    bank_transfer_request = (
                        BankTransferRequest.objects.select_for_update().get(
                            pk=bank_transfer_request.pk,
                            user=request.user,
                            status=BankTransferRequest.Status.APPROVED,
                            entitlement_expires_at__gt=timezone.now(),
                        )
                    )
                    prorated_refund = calculate_prorated_refund(
                        bank_transfer_request,
                        requested_at=now,
                    )
                    refund_request = serializer.save(
                        user=request.user,
                        bank_transfer_request=bank_transfer_request,
                        requested_amount=prorated_refund.amount,
                        currency_code=bank_transfer_request.currency_code,
                        remaining_seconds=prorated_refund.remaining_seconds,
                    )
                else:
                    purchase = PremiumPurchase.objects.select_for_update().get(
                        pk=purchase.pk,
                        user=request.user,
                        status=PremiumPurchase.Status.COMPLETED,
                        revoked_at__isnull=True,
                        entitlement_expires_at__gt=timezone.now(),
                    )
                    prorated_refund = calculate_prorated_refund(
                        purchase,
                        requested_at=now,
                    )
                    refund_request = serializer.save(
                        user=request.user,
                        purchase=purchase,
                        requested_amount=prorated_refund.amount,
                        currency_code=purchase.currency_code,
                        remaining_seconds=prorated_refund.remaining_seconds,
                    )
                refund_request = suspend_refund_access(
                    refund_request,
                    suspended_at=now,
                )
        except (
            PayAppPayment.DoesNotExist,
            PremiumPurchase.DoesNotExist,
            BankTransferRequest.DoesNotExist,
            RefundCalculationError,
        ):
            return self.no_refundable_purchase_response()
        except IntegrityError:
            existing_request = PremiumRefundRequest.objects.get(**source_filter)
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


class PayAppFeedbackView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            validate_payapp_settings()
        except PayAppConfigurationError:
            return HttpResponse(
                "FAIL",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
                content_type="text/plain; charset=utf-8",
            )

        data = (
            request.data.dict()
            if hasattr(request.data, "dict")
            else dict(request.data)
        )
        try:
            process_feedback(data)
        except PayAppFeedbackValidationError as exc:
            logger.warning("PayApp feedback rejected: %s", exc)
            return HttpResponse(
                "FAIL",
                status=status.HTTP_400_BAD_REQUEST,
                content_type="text/plain; charset=utf-8",
            )
        except Exception:
            logger.exception(
                "Unexpected error while processing PayApp feedback.",
                extra={"payapp_mul_no": data.get("mul_no")},
            )
            raise
        return HttpResponse("SUCCESS", content_type="text/plain; charset=utf-8")
