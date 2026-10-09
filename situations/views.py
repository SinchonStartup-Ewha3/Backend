from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import NotificationSchedule
from .serializers import NotificationScheduleSerializer

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.constants import SituationType
from core.serializers import RegionSerializer
from home.services import kma_client as kma
from home.services.kma_client import KmaApiError
from home.services.weather import get_hourly_weather, get_user_grid
from .services.laundry import build_laundry_info

from .services.airkorea import get_air_quality
from .services.running import build_running_info
from .services.uv import get_uv_forecast

class NotificationScheduleListCreateView(generics.ListCreateAPIView):
    serializer_class = NotificationScheduleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return NotificationSchedule.objects.filter(
            user=self.request.user,
        ).select_related("region")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class NotificationScheduleDetailView(
    generics.RetrieveUpdateDestroyAPIView
):
    serializer_class = NotificationScheduleSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "schedule_id"

    def get_queryset(self):
        return NotificationSchedule.objects.filter(
            user=self.request.user,
        ).select_related("region")


class LaundryView(APIView):
    def get(self, request):
        grid = get_user_grid(request.user)
        if grid is None:
            return Response({"detail": "위치를 먼저 설정해주세요."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            hourly = get_hourly_weather(*grid)
        except KmaApiError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        region = RegionSerializer(request.user.region).data if request.user.region else None
        return Response({
            "situation": SituationType.LAUNDRY,
            "region": region,
            **build_laundry_info(hourly, today=kma.now_kst().date()),
        })

class RunningView(APIView):
    def get(self, request):
        grid = get_user_grid(request.user)
        if grid is None:
            return Response({"detail": "위치를 먼저 설정해주세요."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            hourly = get_hourly_weather(*grid)
        except KmaApiError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        region = request.user.region
        return Response({
            "situation": SituationType.RUNNING,
            "region": RegionSerializer(region).data if region else None,
            **build_running_info(
                hourly,
                today=kma.now_kst().date(),
                air=get_air_quality(region),
                uv_forecast=get_uv_forecast(region),
            ),
        })