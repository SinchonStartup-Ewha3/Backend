from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .serializers import (
    LocationUpdateSerializer,
    MeSerializer,
    NicknameUpdateSerializer,
    SocialLoginSerializer,
)

from .services import (
    PROFILE_FETCHERS,
    SocialAuthError,
    get_or_create_social_user,
    withdraw_user,
)

SIX_PLACES = Decimal("0.000001")


def _to_decimal(value: float) -> Decimal:
    return Decimal(str(value)).quantize(SIX_PLACES, rounding=ROUND_HALF_UP)


class SocialLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = SocialLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        provider = serializer.validated_data["provider"]

        fetcher = PROFILE_FETCHERS.get(provider)
        if fetcher is None:
            return Response({"detail": "아직 지원하지 않는 로그인 방식입니다."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            profile = fetcher(serializer.validated_data["access_token"])
        except SocialAuthError as e:
            return Response({"detail": str(e)}, status=e.status_code)

        user, is_new_user = get_or_create_social_user(provider, profile)
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "access_token": str(refresh.access_token),
                "refresh_token": str(refresh),
                "is_new_user": is_new_user,
                "is_onboarded": user.is_onboarded,
            },
            status=status.HTTP_201_CREATED if is_new_user else status.HTTP_200_OK,
        )


class MeView(APIView):
    def get(self, request):
        return Response(MeSerializer(request.user).data)
    
    def delete(self, request):
        withdraw_user(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class LocationUpdateView(APIView):
    def patch(self, request):
        serializer = LocationUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = request.user

        user.location_mode = data["locationMode"]
        user.region = data["region"]
        if data["locationMode"] == User.LocationMode.GPS:
            user.last_lat = _to_decimal(data["lat"])
            user.last_lng = _to_decimal(data["lng"])

        user.refresh_onboarding_status()
        user.save(update_fields=["location_mode", "region", "last_lat", "last_lng", "is_onboarded"])
        return Response(MeSerializer(user).data)


class NicknameUpdateView(APIView):
    def patch(self, request):
        serializer = NicknameUpdateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user

        user.nickname = serializer.validated_data["nickname"]
        user.refresh_onboarding_status()
        try:
            user.save(update_fields=["nickname", "is_onboarded"])
        except IntegrityError:
            # 중복 검사와 저장 사이에 다른 사람이 같은 닉네임을 가져간 경우
            return Response(
                {"nickname": ["이미 사용 중인 닉네임입니다."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(MeSerializer(user).data)