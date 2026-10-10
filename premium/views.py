from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PremiumProfile
from .serializers import PremiumProfileSerializer


class PremiumProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get_profile(self, user):
        # 아직 Paddle 결제를 붙이지 않았으므로 로그인 사용자에게 설정 생성을 허용한다.
        # TODO: Paddle 연동 후 여기 앞에 프리미엄 이용 권한 검사를 추가한다.
        profile, _ = PremiumProfile.objects.get_or_create(user=user)
        return profile

    def get(self, request):
        profile = self.get_profile(request.user)
        return Response(PremiumProfileSerializer(profile).data)

    def put(self, request):
        return self.update_profile(request)

    def patch(self, request):
        return self.update_profile(request, partial=True)

    def update_profile(self, request, partial=False):
        profile = self.get_profile(request.user)
        serializer = PremiumProfileSerializer(
            profile,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)
