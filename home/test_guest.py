"""로그인 없이 쓰는 화면(홈·상황 빨래/러닝·지역 검색) 테스트."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Region

User = get_user_model()

CURRENT = {"temperature": 18.0, "condition": "CLEAR"}


class GuestLocationTests(APITestCase):
    def setUp(self):
        self.region = Region.objects.create(
            region_code="1114055000", region_name="서울특별시 중구 소공동",
            lat="37.563800", lng="126.979500", grid_nx=60, grid_ny=127,
        )
        self.other = Region.objects.create(
            region_code="2638051000", region_name="부산광역시 사하구 괴정1동",
            lat="35.100000", lng="128.990000", grid_nx=96, grid_ny=74,
        )
        self.url = reverse("weather-current")

    @patch("home.views.get_current_weather", return_value=CURRENT)
    def test_guest_with_region_code(self, mock_weather):
        res = self.client.get(self.url, {"regionCode": "1114055000"})

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["region"]["regionCode"], "1114055000")
        mock_weather.assert_called_once_with(60, 127)

    @patch("home.views.get_current_weather", return_value=CURRENT)
    def test_guest_with_lat_lng(self, mock_weather):
        res = self.client.get(self.url, {"lat": "37.5638", "lng": "126.9795"})

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["region"]["regionCode"], "1114055000")
        mock_weather.assert_called_once_with(60, 127)

    def test_guest_without_location(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "LOCATION_REQUIRED")

    def test_invalid_region_code(self):
        res = self.client.get(self.url, {"regionCode": "0000000000"})
        self.assertEqual(res.data["code"], "INVALID_REGION")

    def test_lat_without_lng(self):
        res = self.client.get(self.url, {"lat": "37.5"})
        self.assertEqual(res.data["code"], "INVALID_LOCATION")

    def test_not_a_number(self):
        res = self.client.get(self.url, {"lat": "abc", "lng": "126.9"})
        self.assertEqual(res.data["code"], "INVALID_LOCATION")

    def test_out_of_service_area(self):
        res = self.client.get(self.url, {"lat": "48.85", "lng": "2.35"})  # 파리
        self.assertEqual(res.data["code"], "OUT_OF_SERVICE_AREA")

    @patch("home.views.get_current_weather", return_value=CURRENT)
    def test_logged_in_user_uses_saved_location(self, mock_weather):
        user = User.objects.create_user(nickname="저장위치", region=self.region)
        self.client.force_authenticate(user)

        res = self.client.get(self.url)

        self.assertEqual(res.data["region"]["regionCode"], "1114055000")
        mock_weather.assert_called_once_with(60, 127)

    @patch("home.views.get_current_weather", return_value=CURRENT)
    def test_query_param_overrides_saved_location(self, mock_weather):
        user = User.objects.create_user(nickname="다른지역보기", region=self.region)
        self.client.force_authenticate(user)

        res = self.client.get(self.url, {"regionCode": "2638051000"})

        self.assertEqual(res.data["region"]["regionCode"], "2638051000")
        mock_weather.assert_called_once_with(96, 74)

    @patch("home.views.get_current_weather", return_value=CURRENT)
    def test_logged_in_without_saved_location_can_send_param(self, mock_weather):
        user = User.objects.create_user(nickname="위치없음")
        self.client.force_authenticate(user)

        self.assertEqual(self.client.get(self.url).data["code"], "LOCATION_REQUIRED")
        res = self.client.get(self.url, {"regionCode": "1114055000"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    @patch("situations.views.build_laundry_info", return_value={})
    @patch("situations.views.get_hourly_weather", return_value=[])
    def test_guest_laundry(self, mock_hourly, _):
        res = self.client.get(reverse("situations:laundry"), {"regionCode": "1114055000"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["situation"], "LAUNDRY")
        mock_hourly.assert_called_once_with(60, 127)

    @patch("situations.views.get_uv_forecast", return_value=None)
    @patch("situations.views.get_air_quality", return_value=None)
    @patch("situations.views.build_running_info", return_value={})
    @patch("situations.views.get_hourly_weather", return_value=[])
    def test_guest_running_uses_region_for_air_and_uv(self, _, __, mock_air, mock_uv):
        res = self.client.get(reverse("situations:running"), {"regionCode": "1114055000"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        mock_air.assert_called_once_with(self.region)
        mock_uv.assert_called_once_with(self.region)

    def test_guest_region_search(self):
        res = self.client.get(reverse("region-search"), {"q": "소공동"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data[0]["regionCode"], "1114055000")

    def test_hydration_still_requires_login(self):
        res = self.client.get(reverse("situations:hydration"))
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)