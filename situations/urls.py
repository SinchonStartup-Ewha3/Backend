from django.urls import path

from .views import (
    NotificationScheduleDetailView,
    NotificationScheduleListCreateView,
)


app_name = "situations"

urlpatterns = [
    path(
        "schedules/",
        NotificationScheduleListCreateView.as_view(),
        name="schedule-list-create",
    ),
    path(
        "schedules/<int:schedule_id>/",
        NotificationScheduleDetailView.as_view(),
        name="schedule-detail",
    ),
]