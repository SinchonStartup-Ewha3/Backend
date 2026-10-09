from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import NotificationSchedule
from .serializers import NotificationScheduleSerializer


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