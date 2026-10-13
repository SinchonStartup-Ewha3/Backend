from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Region
from fortune.models import FortuneProfile, FortuneResult
from fortune.services.generator import build_fortune_result, get_or_create_fortune_result
from fortune.services.saju import Element, LuckLevel, day_stem_element, luck_level

User = get_user_model()


class SajuTests(TestCase):
    def test_day_stem_element(self):
        # 2026-10-13은 경신일 → 경(쇠)
        self.assertEqual(day_stem_element(date(2026, 10, 13)), Element.METAL)
        # 2002-05-17은 을유일 → 을(나무)
        self.assertEqual(day_stem_element(date(2002, 5, 17)), Element.WOOD)

    def test_luck_level_relations(self):
        self.assertEqual(luck_level(Element.WOOD, Element.WATER), LuckLevel.GREAT)    # 수생목
        self.assertEqual(luck_level(Element.WOOD, Element.WOOD), LuckLevel.GOOD)      # 같은 기운
        self.assertEqual(luck_level(Element.WOOD, Element.FIRE), LuckLevel.NORMAL)    # 목생화
        self.assertEqual(luck_level(Element.WOOD, Element.EARTH), LuckLevel.CAUTION)  # 목극토
        self.assertEqual(luck_level(Element.WOOD, Element.METAL), LuckLevel.BAD)      # 금극목


class GeneratorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(nickname="운세유저")
        self.profile = FortuneProfile.objects.create(
            user=self.user, calendar_type="SOLAR",
            birth_date="2002-05-17", converted_solar_date=date(2002, 5, 17),
            birth_time_unknown=True,
        )

    def test_same_user_and_date_gives_same_result(self):
        a = build_fortune_result(user=self.user, profile=self.profile, target_date=date(2026, 10, 13))
        b = build_fortune_result(user=self.user, profile=self.profile, target_date=date(2026, 10, 13))
        self.assertEqual(a, b)

    def test_level_from_elements(self):
        # 나무(을유일생) vs 쇠(경신일) → 금극목 → BAD
        result = build_fortune_result(user=self.user, profile=self.profile, target_date=date(2026, 10, 13))
        self.assertEqual(result["luck_level"], LuckLevel.BAD)
        self.assertEqual(result["title"], "오늘 운수 안좋은 테루테루")
        self.assertIn("'물과'", result["detail_text"])  # 나무를 도와주는 건 물

    def test_rain_changes_item_and_detail(self):
        result = build_fortune_result(
            user=self.user, profile=self.profile, target_date=date(2026, 10, 13), weather="RAIN",
        )
        self.assertIn(result["lucky_item"], ["투명우산", "레인부츠", "방수 파우치"])
        self.assertIn("비가 오는 날", result["detail_text"])

    def test_without_location_weather_is_none(self):
        result = get_or_create_fortune_result(user=self.user, target_date=date(2026, 10, 13))
        self.assertIsNone(result.weather_condition)

    @patch("home.services.weather.get_current_weather", side_effect=RuntimeError("기상청 오류"))
    def test_weather_error_falls_back(self, _):
        region = Region.objects.create(
            region_code="1114055000", region_name="서울특별시 중구 소공동",
            lat="37.5638", lng="126.9795", grid_nx=60, grid_ny=127,
        )
        self.user.region = region
        self.user.save()

        result = get_or_create_fortune_result(user=self.user, target_date=date(2026, 10, 13))

        self.assertIsNone(result.weather_condition)
        self.assertTrue(result.lucky_item)


class TodayFortuneAPITests(APITestCase):
    def setUp(self):
        self.region = Region.objects.create(
            region_code="1114055000", region_name="서울특별시 중구 소공동",
            lat="37.5638", lng="126.9795", grid_nx=60, grid_ny=127,
        )
        self.user = User.objects.create_user(nickname="오늘운세", region=self.region)
        FortuneProfile.objects.create(
            user=self.user, calendar_type="SOLAR",
            birth_date="2002-05-17", converted_solar_date=date(2002, 5, 17),
            birth_time_unknown=True,
        )
        self.client.force_authenticate(self.user)

    @patch("home.services.weather.get_current_weather", return_value={"condition": "RAIN"})
    def test_today_includes_luck_and_weather(self, mock_weather):
        res = self.client.get(reverse("today-fortune-result"))

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(res.data["luck_level"], LuckLevel.values)
        self.assertTrue(res.data["luck_label"])
        self.assertTrue(res.data["summary"])
        self.assertEqual(res.data["weather_condition"], "RAIN")
        self.assertEqual(res.data["weather_label"], "비오는 하루")
        self.assertIsNone(res.data["detail_text"])  # 무료는 상세 풀이 잠김

    @patch("home.services.weather.get_current_weather", return_value={"condition": "RAIN"})
    def test_weather_is_fetched_once_per_day(self, mock_weather):
        self.client.get(reverse("today-fortune-result"))
        self.client.get(reverse("today-fortune-result"))

        self.assertEqual(mock_weather.call_count, 1)
        self.assertEqual(FortuneResult.objects.filter(user=self.user).count(), 1)