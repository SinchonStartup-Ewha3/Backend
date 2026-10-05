from django.urls import path
from .views import CurrentWeatherView, HourlyWeatherView

urlpatterns = [
    path("weather/current/", CurrentWeatherView.as_view(), name="weather-current"),
    path("weather/hourly/", HourlyWeatherView.as_view(), name="weather-hourly"),
]