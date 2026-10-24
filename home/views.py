from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.serializers import RegionSerializer
from .services.kma_client import KmaApiError
from .services.life_info import build_life_info
from .services.location import LocationError, resolve_location
from .services.weather import get_current_weather, get_hourly_weather


class _WeatherBaseView(APIView):
    """로그인 없이 볼 수 있다. 비로그인은 ?regionCode= 또는 ?lat=&lng=로 위치를 보낸다."""

    permission_classes = [AllowAny]

    def get(self, request):
        try:
            location = resolve_location(request)
        except LocationError as e:
            return Response(e.to_response_data(), status=e.status)
        try:
            data = self.build(*location.grid)
        except KmaApiError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        region = RegionSerializer(location.region).data if location.region else None
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