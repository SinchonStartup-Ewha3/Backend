from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import NotificationSchedule, WaterIntake
from .serializers import NotificationScheduleSerializer, WaterIntakeCreateSerializer

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.constants import SituationType
from core.serializers import RegionSerializer
from home.services import kma_client as kma
from home.services.kma_client import KmaApiError
from home.services.weather import get_hourly_weather, get_user_grid, get_current_weather
from .services.laundry import build_laundry_info

from .services.airkorea import get_air_quality
from .services.running import build_running_info
from .services.uv import get_uv_forecast
from .services.hydration import build_hydration_summary

from datetime import datetime

from django.shortcuts import get_object_or_404

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

def _weather_or_none(user):
    """수분 화면은 날씨가 없어도 동작해야 하므로 실패하면 None"""
    grid = get_user_grid(user)
    if grid is None:
        return None
    try:
        return get_current_weather(*grid)
    except KmaApiError:
        return None


def _hydration_response(request, status_code=status.HTTP_200_OK):
    today = kma.now_kst().date()
    records = list(
        WaterIntake.objects.filter(user=request.user, drank_at__date=today)
    )
    return Response(
        {
            "situation": SituationType.HYDRATION,
            **build_hydration_summary(records, _weather_or_none(request.user), today),
        },
        status=status_code,
    )


class HydrationView(APIView):
    def get(self, request):
        return _hydration_response(request)


class HydrationRecordCreateView(APIView):
    def post(self, request):
        serializer = WaterIntakeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        now = kma.now_kst()
        drank_at = datetime.combine(now.date(), serializer.validated_data["time"], tzinfo=kma.KST)
        if drank_at > now:
            return Response({"time": ["아직 지나지 않은 시간은 기록할 수 없어요."]},
                            status=status.HTTP_400_BAD_REQUEST)

        WaterIntake.objects.create(
            user=request.user,
            drank_at=drank_at,
            amount_ml=serializer.validated_data["amountMl"],
        )
        return _hydration_response(request, status.HTTP_201_CREATED)


class HydrationRecordDeleteView(APIView):
    def delete(self, request, record_id):
        record = get_object_or_404(WaterIntake, pk=record_id, user=request.user)
        record.delete()
        return _hydration_response(request)