from django.shortcuts import render

# Create your views here.
# home/views.py
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from core.geo import latlng_to_grid
from core.serializers import RegionSerializer
from .services.kma_client import KmaApiError
from .services.weather import get_current_weather, get_hourly_weather


def _user_grid(user) -> tuple[int, int] | None:
    """GPS 사용자는 실제 좌표, 직접 선택한 사용자는 지역 중심 좌표로 격자를 구한다"""
    if user.location_mode == User.LocationMode.GPS and user.last_lat is not None:
        return latlng_to_grid(user.last_lat, user.last_lng)
    if user.region is not None:
        return user.region.grid_nx, user.region.grid_ny
    return None


class _WeatherBaseView(APIView):
    def get(self, request):
        grid = _user_grid(request.user)
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