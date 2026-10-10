from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from fortune.models import FortuneProfile, FortunePurchase, FortuneResult
from premium.models import PremiumProfile
from situations.models import NotificationSchedule

from .serializers import MyPageFortuneProfileSerializer


class MyPageSummaryView(APIView):
    """마이페이지 첫 화면에 필요한 정보를 한 번에 반환한다."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        premium_profile = PremiumProfile.objects.filter(
            user=user,
        ).first()

        notification_settings = {
            "outer": (
                premium_profile is not None
                and premium_profile.cold_sensitivity
                != PremiumProfile.ColdSensitivity.UNKNOWN
            ),
            "exercise": (
                premium_profile is not None
                and premium_profile.exercise_preference
                != PremiumProfile.ExercisePreference.NO_NOTIFICATION
            ),
            "laundry": (
                premium_profile is not None
                and any([
                    premium_profile.laundry_rain_alert,
                    premium_profile.laundry_humidity_alert,
                    premium_profile.laundry_indoor_tip,
                ])
            ),
            "umbrella": NotificationSchedule.objects.filter(
                user=user,
                is_enabled=True,
            ).exists(),
        }

        region = user.region

        return Response({
            "profile": {
                "nickname": user.nickname,
                "profileImage": user.profile_image,
                "region": (
                    {
                        "regionCode": region.region_code,
                        "regionName": region.region_name,
                    }
                    if region is not None
                    else None
                ),
            },
            # 실제 구독 모델이 추가되기 전까지 null은 무료 사용자를 뜻한다.
            "subscription": None,
            "notificationSettings": notification_settings,
        })


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
