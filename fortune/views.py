from datetime import timedelta

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    FortuneProduct,
    FortuneProfile,
    FortunePurchase,
    FortuneResult,
)
from .serializers import (
    FortuneProductSerializer,
    FortuneProfileSerializer,
    FortunePurchaseCreateSerializer,
    FortunePurchaseSerializer,
    FortuneResultSerializer,
)
from .services.generator import get_or_create_fortune_result
from .services.payments import (
    PaymentConfirmationError,
    PaymentGatewayNotConfigured,
    confirm_payment,
)


class FortuneProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = FortuneProfile.objects.filter(user=request.user).first()
        if profile is None:
            return Response(
                {
                    "detail": "생년월일 정보가 없습니다.",
                    "code": "FORTUNE_PROFILE_NOT_FOUND",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(FortuneProfileSerializer(profile).data)

    def post(self, request):
        if FortuneProfile.objects.filter(user=request.user).exists():
            return Response(
                {
                    "detail": "생년월일 정보가 이미 등록되어 있습니다. 마이페이지에서 수정해주세요.",
                    "code": "FORTUNE_PROFILE_ALREADY_EXISTS",
                },
                status=status.HTTP_409_CONFLICT,
            )

        serializer = FortuneProfileSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class FortuneProductListView(generics.ListAPIView):
    serializer_class = FortuneProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return FortuneProduct.objects.filter(is_active=True)


class FortunePurchaseCreateView(generics.CreateAPIView):
    serializer_class = FortunePurchaseCreateSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        purchase = serializer.save()

        return Response(
            FortunePurchaseSerializer(purchase).data,
            status=status.HTTP_201_CREATED,
        )


class FortunePaymentConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def build_success_response(purchase):
        result = get_or_create_fortune_result(
            user=purchase.user,
            target_date=timezone.localdate(),
            profile=purchase,
        )
        return Response(
            {
                "purchase": FortunePurchaseSerializer(purchase).data,
                "result": FortuneResultSerializer(
                    result,
                    context={"can_view_detail": True},
                ).data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request, purchase_id):
        purchase = get_object_or_404(
            FortunePurchase,
            id=purchase_id,
            user=request.user,
        )

        if purchase.payment_status == FortunePurchase.PaymentStatus.PAID:
            today = timezone.localdate()
            if not (
                purchase.active_from
                and purchase.active_until
                and purchase.active_from <= today <= purchase.active_until
            ):
                return Response(
                    {
                        "detail": "운세 상품 이용 기간이 종료되었습니다.",
                        "code": "FORTUNE_PURCHASE_EXPIRED",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            return self.build_success_response(purchase)

        payment_key = request.data.get("payment_key")
        if not payment_key:
            raise ValidationError({
                "payment_key": "결제 키가 필요합니다."
            })

        try:
            confirmation = confirm_payment(
                payment_key=payment_key,
                order_id=str(purchase.id),
                amount=purchase.amount,
            )
        except PaymentGatewayNotConfigured as exc:
            return Response(
                {
                    "detail": str(exc),
                    "code": "PAYMENT_GATEWAY_NOT_CONFIGURED",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except PaymentConfirmationError as exc:
            raise ValidationError({"payment": str(exc)}) from exc

        if (
            confirmation.status != "DONE"
            or confirmation.amount != purchase.amount
            or confirmation.order_id != str(purchase.id)
        ):
            raise ValidationError({
                "payment": "결제 승인 정보가 주문과 일치하지 않습니다."
            })

        today = timezone.localdate()

        with transaction.atomic():
            locked_purchase = (
                FortunePurchase.objects
                .select_for_update()
                .select_related("user")
                .get(id=purchase.id)
            )

            if locked_purchase.payment_status == FortunePurchase.PaymentStatus.PAID:
                purchase = locked_purchase
            else:
                locked_purchase.payment_key = confirmation.payment_key
                locked_purchase.payment_status = (
                    FortunePurchase.PaymentStatus.PAID
                )
                locked_purchase.purchased_at = timezone.now()
                locked_purchase.active_from = today
                locked_purchase.active_until = (
                    today
                    + timedelta(
                        days=locked_purchase.duration_days - 1
                    )
                )
                locked_purchase.save()
                purchase = locked_purchase

        return self.build_success_response(purchase)


class TodayFortuneResultView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.localdate()
        profile = FortuneProfile.objects.filter(user=request.user).first()
        if profile is None:
            return Response(
                {
                    "detail": "생년월일 정보를 먼저 입력해주세요.",
                    "code": "FORTUNE_PROFILE_REQUIRED",
                },
                status=status.HTTP_409_CONFLICT,
            )

        active_purchase = (
            FortunePurchase.objects.filter(
                user=request.user,
                payment_status=FortunePurchase.PaymentStatus.PAID,
                active_from__lte=today,
                active_until__gte=today,
            )
            .order_by("-purchased_at")
            .first()
        )

        result = get_or_create_fortune_result(
            user=request.user,
            target_date=today,
            profile=active_purchase or profile,
        )

        return Response(
            FortuneResultSerializer(
                result,
                context={"can_view_detail": active_purchase is not None},
            ).data,
            status=status.HTTP_200_OK,
        )


class PurchaseFortuneResultListView(generics.ListAPIView):
    serializer_class = FortuneResultSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        today = timezone.localdate()
        purchase = get_object_or_404(
            FortunePurchase,
            id=self.kwargs["purchase_id"],
            user=self.request.user,
            payment_status=FortunePurchase.PaymentStatus.PAID,
        )

        return FortuneResult.objects.filter(
            user=self.request.user,
            target_date__gte=purchase.active_from,
            target_date__lte=min(today, purchase.active_until),
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["can_view_detail"] = True
        return context
