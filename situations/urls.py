from django.urls import path

from .views import (
    LaundryView,
    RunningView,
    HydrationView,
    HydrationRecordCreateView,
    HydrationRecordDeleteView,
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
    path("laundry/", LaundryView.as_view(), name="laundry"),
    path("running/", RunningView.as_view(), name="running"),
    path("hydration/", HydrationView.as_view(), name="hydration"),
    path("hydration/records/", HydrationRecordCreateView.as_view(), name="hydration-record-create"),
    path("hydration/records/<int:record_id>/", HydrationRecordDeleteView.as_view(), name="hydration-record-delete"),
]