from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from core.models import Region

from .services.weather_copy import (
    _fallback_copy,
    build_community_weather_copy,
)


User = get_user_model()


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
class CommunityWeatherCopyTests(TestCase):
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
            region, result = build_community_weather_copy(self.user)

        self.assertEqual(region, self.region)
        self.assertEqual(result["headline"]["source"], "FALLBACK")
        mock_current_weather.assert_called_once_with(60, 127)
        mock_hourly_weather.assert_called_once_with(60, 127, hours=24)
        mock_generate_copy.assert_called_once()
