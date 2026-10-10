from django.db import models


class WeatherCondition(models.TextChoices):
    CLEAR = "CLEAR", "맑음"
    PARTLY_CLOUDY = "PARTLY_CLOUDY", "구름많음"
    CLOUDY = "CLOUDY", "흐림"
    RAIN = "RAIN", "비"
    SLEET = "SLEET", "비/눈"
    SNOW = "SNOW", "눈"
    SHOWER = "SHOWER", "소나기"

class SituationType(models.TextChoices):
    HYDRATION = "HYDRATION", "수분"
    LAUNDRY = "LAUNDRY", "빨래"
    RUNNING = "RUNNING", "러닝"