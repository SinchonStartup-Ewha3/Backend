from django.urls import path
from .views import RegionSearchView

urlpatterns = [
    path("", RegionSearchView.as_view(), name="region-search"),
]