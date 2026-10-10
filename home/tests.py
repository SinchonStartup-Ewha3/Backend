from django.test import TestCase

# Create your tests here.
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Region
from .services import kma_client as kma
from .services.weather import feels_like, to_condition
from .services.life_info import CharacterState, build_life_info

User = get_user_model()
FIXED_NOW = datetime(2026, 10, 5, 14, 30, tzinfo=kma.KST)


def fake_request(operation, base_date, base_time, nx, ny):
    if operation == "getUltraSrtNcst":
        return [
            {"category": "T1H", "obsrValue": "19.2"},
            {"category": "REH", "obsrValue": "60"},
            {"category": "WSD", "obsrValue": "1.5"},
            {"category": "PTY", "obsrValue": "0"},
            {"category": "RN1", "obsrValue": "0"},
        ]

    items = [
        {"category": "TMN", "fcstDate": "20261005", "fcstTime": "0600", "fcstValue": "19.0"},
        {"category": "TMX", "fcstDate": "20261005", "fcstTime": "1500", "fcstValue": "30.0"},
    ]
    start = FIXED_NOW.replace(minute=0) + timedelta(hours=1)
    for i in range(30):
        dt = start + timedelta(hours=i)
        for category, value in (("TMP", "21"), ("SKY", "1"), ("PTY", "0"), ("POP", "10")):
            items.append({
                "category": category,
                "fcstDate": dt.strftime("%Y%m%d"),
                "fcstTime": dt.strftime("%H00"),
                "fcstValue": value,
            })
    return items


class BaseTimeTests(SimpleTestCase):
    def test_ncst_uses_previous_hour_before_40_minutes(self):
        now = datetime(2026, 10, 5, 14, 30, tzinfo=kma.KST)
        self.assertEqual(kma.ultra_srt_ncst_base(now), ("20261005", "1300"))

    def test_vilage_uses_latest_released_base(self):
        now = datetime(2026, 10, 5, 14, 30, tzinfo=kma.KST)
        self.assertEqual(kma.vilage_fcst_base(now), ("20261005", "1400"))

    def test_vilage_uses_yesterday_before_first_release(self):
        now = datetime(2026, 10, 5, 1, 0, tzinfo=kma.KST)
        self.assertEqual(kma.vilage_fcst_base(now), ("20261004", "2300"))


class WeatherLogicTests(SimpleTestCase):
    def test_precipitation_overrides_sky(self):
        self.assertEqual(to_condition("1", "1"), "RAIN")
        self.assertEqual(to_condition("4", "0"), "CLOUDY")

    def test_winter_wind_lowers_feels_like(self):
        self.assertLess(feels_like(0, 50, 5, month=1), 0)


@patch("home.services.kma_client.now_kst", return_value=FIXED_NOW)
@patch("home.services.kma_client._request", side_effect=fake_request)
class WeatherAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        region = Region.objects.create(
            region_code="1114055000", region_name="서울특별시 중구 소공동",
            lat="37.563800", lng="126.979500", grid_nx=60, grid_ny=127,
        )
        self.user = User.objects.create_user(nickname="날씨요정", region=region)
        self.client.force_authenticate(user=self.user)

    def test_current_weather(self, *_):
        response = self.client.get(reverse("weather-current"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["temperature"], 19.2)
        self.assertEqual(response.data["minTemperature"], 19.0)
        self.assertEqual(response.data["maxTemperature"], 30.0)
        self.assertEqual(response.data["condition"], "CLEAR")

    def test_hourly_weather_returns_24_hours(self, *_):
        response = self.client.get(reverse("weather-hourly"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["items"]), 24)
        self.assertEqual(response.data["items"][0]["hour"], 15)

    def test_location_required(self, *_):
        self.user.region = None
        self.user.save()
        response = self.client.get(reverse("weather-current"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_kma_error_returns_502(self, mock_request, _):
        mock_request.side_effect = kma.KmaApiError("기상청 서버와 통신에 실패했습니다.")
        response = self.client.get(reverse("weather-current"))
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)

def make_current(**overrides):
    base = {
        "temperature": 18.0, "feelsLike": 18.0, "minTemperature": 14.0,
        "maxTemperature": 20.0, "windSpeed": 1.0, "precipitation": 0.0,
        "condition": "CLEAR", "isNight": False,
    }
    base.update(overrides)
    return base


def make_hourly(rain_at: int | None = None, start_hour: int = 15):
    items = []
    for i in range(24):
        hour = (start_hour + i) % 24
        rainy = rain_at is not None and i == rain_at
        items.append({
            "hour": hour,
            "condition": "RAIN" if rainy else "CLEAR",
            "precipitationProbability": 80.0 if rainy else 0.0,
        })
    return items


class LifeInfoTests(SimpleTestCase):
    def test_raining_now(self):
        info = build_life_info(make_current(condition="RAIN"), make_hourly())
        self.assertEqual(info.character, CharacterState.RAINY)
        self.assertTrue(info.umbrella_needed)

    def test_rain_later_today(self):
        info = build_life_info(make_current(), make_hourly(rain_at=3))
        self.assertEqual(info.rain_from_hour, 18)
        self.assertIn("18시", info.message)
        self.assertEqual(info.character, CharacterState.DEFAULT)  # 지금은 안 옴

    def test_rain_beyond_12_hours_is_ignored(self):
        info = build_life_info(make_current(), make_hourly(rain_at=20))
        self.assertFalse(info.umbrella_needed)

    def test_chilly_message(self):
        info = build_life_info(make_current(feelsLike=8.0, minTemperature=6.0, maxTemperature=12.0), make_hourly())
        self.assertEqual(info.message, "날씨가 제법 쌀쌀하니 감기에 조심하세요!")

    def test_cold_character_and_padding(self):
        info = build_life_info(make_current(feelsLike=-3.0), make_hourly())
        self.assertEqual(info.character, CharacterState.COLD)
        self.assertEqual(info.outfit_code, "PADDED")

    def test_rain_beats_cold_message(self):
        info = build_life_info(make_current(feelsLike=3.0), make_hourly(rain_at=1))
        self.assertIn("비 소식", info.message)

    def test_big_temp_gap(self):
        info = build_life_info(make_current(minTemperature=8.0, maxTemperature=22.0), make_hourly())
        self.assertEqual(info.temp_gap, 14.0)
        self.assertIn("일교차", info.message)


@patch("home.services.kma_client.now_kst", return_value=FIXED_NOW)
@patch("home.services.kma_client._request", side_effect=fake_request)
class HomeAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        region = Region.objects.create(
            region_code="1114055000", region_name="서울특별시 중구 소공동",
            lat="37.563800", lng="126.979500", grid_nx=60, grid_ny=127,
        )
        self.user = User.objects.create_user(nickname="날씨요정", region=region)
        self.client.force_authenticate(user=self.user)

    def test_home_returns_all_sections(self, *_):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for key in ("region", "weather", "hourly", "character", "message", "lifeInfo"):
            self.assertIn(key, response.data)
        self.assertEqual(len(response.data["hourly"]), 24)