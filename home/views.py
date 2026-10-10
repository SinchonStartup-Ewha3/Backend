# home/views.py 전체 교체
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.serializers import RegionSerializer
from .services.kma_client import KmaApiError
from .services.life_info import build_life_info
from .services.weather import get_current_weather, get_hourly_weather, get_user_grid


class _WeatherBaseView(APIView):
    def get(self, request):
        grid = get_user_grid(request.user)
        if grid is None:
            return Response({"detail": "위치를 먼저 설정해주세요."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            data = self.build(*grid)
        except KmaApiError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        region = RegionSerializer(request.user.region).data if request.user.region else None
        return Response({"region": region, **data})


class CurrentWeatherView(_WeatherBaseView):
    def build(self, nx, ny):
        return get_current_weather(nx, ny)


class HourlyWeatherView(_WeatherBaseView):
    def build(self, nx, ny):
        return {"items": get_hourly_weather(nx, ny)}


class HomeView(_WeatherBaseView):
    """홈 화면 진입 시 한 번에 필요한 데이터"""

    def build(self, nx, ny):
        current = get_current_weather(nx, ny)
        hourly = get_hourly_weather(nx, ny)
        return {
            "weather": current,
            "hourly": hourly,
            **build_life_info(current, hourly).to_dict(),
        }