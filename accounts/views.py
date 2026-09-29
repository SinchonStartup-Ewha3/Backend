from django.shortcuts import render

# Create your views here.
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import SocialLoginSerializer
from .services import PROFILE_FETCHERS, SocialAuthError, get_or_create_social_user


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