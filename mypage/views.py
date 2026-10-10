from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from fortune.models import FortuneProfile, FortunePurchase, FortuneResult

from .serializers import MyPageFortuneProfileSerializer


class MyPageFortuneProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get_profile(self, request):
        return FortuneProfile.objects.filter(user=request.user).first()

    def get(self, request):
        profile = self.get_profile(request)
        if profile is None:
            return Response(
                {
                    "detail": "생년월일 정보가 없습니다.",
                    "code": "FORTUNE_PROFILE_NOT_FOUND",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(MyPageFortuneProfileSerializer(profile).data)

    def put(self, request):
        profile = self.get_profile(request)
        if profile is None:
            return Response(
                {
                    "detail": "먼저 오늘의 운세에서 생년월일을 등록해주세요.",
                    "code": "FORTUNE_PROFILE_NOT_FOUND",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        previous_values = (
            profile.calendar_type,
            profile.birth_date,
            profile.birth_time,
            profile.birth_time_unknown,
        )
        serializer = MyPageFortuneProfileSerializer(
            instance=profile,
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        saved_profile = serializer.save()

        current_values = (
            saved_profile.calendar_type,
            saved_profile.birth_date,
            saved_profile.birth_time,
            saved_profile.birth_time_unknown,
        )
        if previous_values != current_values:
            today = timezone.localdate()
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

            # 무료 결과는 수정된 정보로 다시 생성합니다. 이용 중인 유료 결과는
            # 결제 당시 생년월일 스냅샷을 이용권 종료일까지 유지합니다.
            invalidate_from = (
                active_purchase.active_until + timedelta(days=1)
                if active_purchase is not None
                else today
            )
            FortuneResult.objects.filter(
                user=request.user,
                target_date__gte=invalidate_from,
            ).delete()

        return Response(serializer.data, status=status.HTTP_200_OK)
