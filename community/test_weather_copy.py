from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Region

from .services.weather_copy import (
    _fallback_copy,
    build_community_weather_copy,
)


User = get_user_model()

COPY_DATA = {
    "headline": {
        "title": "오늘의 날씨",
        "description": "가디건을 추천해요",
        "source": "WEATHER",
    },
    "premiumCard": {
        "actionType": "WEATHER",
        "message": "날씨를 확인해보세요",
        "subMessage": "알림 기능을 사용해보세요",
        "targetUrl": "/premium",
    },
}


def _life_info():
    return SimpleNamespace(
        character=SimpleNamespace(value="DEFAULT"),
        umbrella_needed=False,
        outfit_label="가디건",
        message="산책하기 좋은 날씨예요!",
    )


class FallbackCopyTests(SimpleTestCase):
    @patch(
        "community.services.weather_copy.build_life_info",
        return_value=_life_info(),
    )
    def test_uses_default_when_temperature_values_are_none(
        self,
        _mock_build_life_info,
    ):
        result = _fallback_copy(
            {
                "temperature": None,
                "feelsLike": None,
                "humidity": 50,
                "condition": "CLEAR",
            },
            [],
        )

        self.assertEqual(
            result["headlineTitle"],
            "가볍게 외출하기 좋은 오늘",
        )

    @patch(
        "community.services.weather_copy.build_life_info",
        return_value=_life_info(),
    )
    def test_keeps_zero_degree_temperature(
        self,
        _mock_build_life_info,
    ):
        result = _fallback_copy(
            {
                "temperature": 12,
                "feelsLike": 0,
                "humidity": 50,
                "condition": "CLEAR",
            },
            [],
        )

        self.assertEqual(
            result["headlineTitle"],
            "기온이 뚝 떨어진 오늘",
        )
        self.assertEqual(result["actionType"], "COLD")


@override_settings(COMMUNITY_WEATHER_COPY_CACHE_SECONDS=300)
class CommunityWeatherCopyTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.region = Region.objects.create(
            region_code="1114055000",
            region_name="서울특별시 중구 소공동",
            lat="37.563800",
            lng="126.979500",
            grid_nx=60,
            grid_ny=127,
        )
        self.user = User.objects.create_user(
            nickname="테스트사용자",
            region=self.region,
        )

    def tearDown(self):
        cache.clear()

    def test_network_calls_are_mocked_and_fallback_is_returned(self):
        current_weather = {
            "temperature": 18,
            "feelsLike": 18,
            "humidity": 50,
            "condition": "CLEAR",
        }

        with (
            patch(
                "community.services.weather_copy.get_current_weather",
                return_value=current_weather,
            ) as mock_current_weather,
            patch(
                "community.services.weather_copy.get_hourly_weather",
                return_value=[],
            ) as mock_hourly_weather,
            patch(
                "community.services.weather_copy._recent_consistent_posts",
                return_value=[],
            ),
            patch(
                "community.services.weather_copy.build_life_info",
                return_value=_life_info(),
            ),
            patch(
                "community.services.weather_copy.generate_community_copy",
                return_value=None,
            ) as mock_generate_copy,
        ):
            region, result = build_community_weather_copy(
                region=self.region,
                grid=(60, 127),
            )

        self.assertEqual(region, self.region)
        self.assertEqual(result["headline"]["source"], "FALLBACK")
        self.assertEqual(
            result["headline"]["title"],
            "가볍게 외출하기 좋은 오늘",
        )
        self.assertEqual(
            result["premiumCard"]["message"],
            "오늘은 빨래하기 좋은 날씨예요",
        )
        self.assertNotIn(
            self.user.nickname,
            result["headline"]["title"],
        )
        self.assertNotIn(
            self.user.nickname,
            result["premiumCard"]["message"],
        )
        mock_current_weather.assert_called_once_with(60, 127)
        mock_hourly_weather.assert_called_once_with(60, 127, hours=24)
        mock_generate_copy.assert_called_once()

    @patch("community.views.build_community_weather_copy")
    def test_guest_can_use_region_code(self, mock_build_copy):
        mock_build_copy.return_value = (self.region, COPY_DATA)

        response = self.client.get(
            reverse("community:weather-copy"),
            {"regionCode": self.region.region_code},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_build_copy.assert_called_once_with(
            region=self.region,
            grid=(60, 127),
        )

    @patch("community.views.build_community_weather_copy")
    def test_guest_can_use_lat_lng(self, mock_build_copy):
        mock_build_copy.return_value = (self.region, COPY_DATA)

        response = self.client.get(
            reverse("community:weather-copy"),
            {"lat": "37.5638", "lng": "126.9795"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_build_copy.assert_called_once_with(
            region=self.region,
            grid=(60, 127),
        )

    def test_guest_without_location_is_rejected(self):
        response = self.client.get(
            reverse("community:weather-copy")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            response.data["code"],
            "COMMUNITY_LOCATION_REQUIRED",
        )

    @patch("community.views.build_community_weather_copy")
    def test_logged_in_user_can_use_saved_region(self, mock_build_copy):
        mock_build_copy.return_value = (self.region, COPY_DATA)
        self.client.force_authenticate(user=self.user)

        response = self.client.get(
            reverse("community:weather-copy")
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_build_copy.assert_called_once_with(
            region=self.region,
            grid=(60, 127),
        )
