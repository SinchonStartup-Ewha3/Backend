from django.urls import path
from .views import CurrentWeatherView, HomeView, HourlyWeatherView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("weather/current/", CurrentWeatherView.as_view(), name="weather-current"),
    path("weather/hourly/", HourlyWeatherView.as_view(), name="weather-hourly"),
]