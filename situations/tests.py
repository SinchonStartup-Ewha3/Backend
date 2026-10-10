import requests
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from situations.services.liner_client import generate_notification_copy

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Region
from situations.services.laundry import build_laundry_info

from home.services.life_info import get_outfit
from premium.models import PremiumProfile
from situations.services.recommendations import (
    OUTFIT_MESSAGES,
    recommend_outfit,
    will_rain,
)

from situations.services.airkorea import PM10_LIMITS, grade_of
from situations.services.running import build_running_info
from situations.services.uv import summarize_uv, uv_grade

from situations.models import WaterIntake
from situations.services.hydration import intake_message, recommended_ml


KST = ZoneInfo("Asia/Seoul")
TODAY = date(2026, 10, 10)
FIXED_NOW = datetime(2026, 10, 10, 21, 10, tzinfo=KST)

class LinerNotificationCopyTests(SimpleTestCase):
    """LINER 문구 생성과 fallback 동작을 검증합니다."""

    @override_settings(
        LINER_ENABLED=False,
        LINER_API_KEY="",
    )
    @patch("situations.services.liner_client.requests.post")
    def test_returns_fallback_when_liner_is_disabled(
        self,
        mocked_post,
    ):
        result = generate_notification_copy(
            notification_type="OUTING_WEATHER",
            weather_context={
                "temperature": 12,
                "condition": "RAIN",
            },
            fallback_title="기본 제목",
            fallback_body="기본 내용",
        )

        self.assertEqual(
            result,
            ("기본 제목", "기본 내용"),
        )

        # 비활성화 상태에서는 LINER에 요청하면 안 됩니다.
        mocked_post.assert_not_called()

    @override_settings(
        LINER_ENABLED=True,
        LINER_API_KEY="test-api-key",
        LINER_API_URL="https://platform.liner.com/api/v1/responses",
        LINER_MODEL="liner-mark",
        LINER_TIMEOUT_SECONDS=10,
    )
    @patch("situations.services.liner_client.requests.post")
    def test_returns_generated_copy_when_liner_succeeds(
        self,
        mocked_post,
    ):
        mocked_response = mocked_post.return_value
        mocked_response.raise_for_status.return_value = None
        mocked_response.json.return_value = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": (
                                '{"title":"비 소식이 있어요",'
                                '"body":"외출할 때 우산을 챙겨주세요."}'
                            ),
                        }
                    ],
                }
            ]
        }

        result = generate_notification_copy(
            notification_type="OUTING_WEATHER",
            weather_context={
                "temperature": 12,
                "condition": "RAIN",
            },
            fallback_title="기본 제목",
            fallback_body="기본 내용",
        )

        self.assertEqual(
            result,
            (
                "비 소식이 있어요",
                "외출할 때 우산을 챙겨주세요.",
            ),
        )

        mocked_post.assert_called_once()

        # API Key가 요청 본문이 아닌 인증 헤더로 전달되는지 확인합니다.
        request_kwargs = mocked_post.call_args.kwargs

        self.assertEqual(
            request_kwargs["headers"]["Authorization"],
            "Bearer test-api-key",
        )

    @override_settings(
        LINER_ENABLED=True,
        LINER_API_KEY="test-api-key",
        LINER_API_URL="https://platform.liner.com/api/v1/responses",
        LINER_MODEL="liner-mark",
        LINER_TIMEOUT_SECONDS=10,
    )
    @patch(
        "situations.services.liner_client.requests.post",
        side_effect=requests.Timeout,
    )
    def test_returns_fallback_when_liner_fails(
        self,
        mocked_post,
    ):
        result = generate_notification_copy(
            notification_type="LAUNDRY",
            weather_context={
                "humidity": 80,
            },
            fallback_title="습도가 높아요",
            fallback_body="실내 건조를 추천해요.",
        )

        self.assertEqual(
            result,
            (
                "습도가 높아요",
                "실내 건조를 추천해요.",
            ),
        )

        mocked_post.assert_called_once()


def make_hourly(start_hour=8, humidity=35, pop=0, condition="CLEAR", wind=2.5):
    start = datetime(TODAY.year, TODAY.month, TODAY.day, start_hour, tzinfo=KST)
    items = []
    for i in range(24):
        dt = start + timedelta(hours=i)
        items.append({
            "time": dt.isoformat(), "hour": dt.hour, "condition": condition,
            "precipitationProbability": pop, "humidity": humidity, "windSpeed": wind,
        })
    return items


class LaundryLogicTests(SimpleTestCase):
    def test_dry_clear_day(self):
        info = build_laundry_info(make_hourly(), today=TODAY)
        self.assertGreaterEqual(info["score"], 80)
        self.assertEqual(info["recommendedTime"], {"start": "11:00", "end": "14:00"})
        self.assertTrue(info["summary"].startswith("오늘은"))

    def test_rain_caps_score(self):
        hourly = make_hourly()
        rainy = next(i for i in hourly if i["hour"] == 13)
        rainy.update(condition="RAIN", precipitationProbability=80)
        info = build_laundry_info(hourly, today=TODAY)
        self.assertLessEqual(info["score"], 30)
        self.assertIn("실내", info["summary"])

    def test_picks_dry_window(self):
        hourly = make_hourly(humidity=85)
        for item in hourly:
            if 11 <= item["hour"] <= 13:
                item["humidity"] = 35
        info = build_laundry_info(hourly, today=TODAY)
        self.assertEqual(info["recommendedTime"], {"start": "11:00", "end": "14:00"})

    def test_evening_shows_tomorrow(self):
        info = build_laundry_info(make_hourly(start_hour=18), today=TODAY)
        self.assertEqual(info["targetDate"], "2026-10-11")
        self.assertTrue(info["summary"].startswith("내일은"))


@patch("situations.views.get_hourly_weather")
class LaundryAPITests(APITestCase):
    def setUp(self):
        region = Region.objects.create(
            region_code="1114055000", region_name="서울특별시 중구 소공동",
            lat="37.563800", lng="126.979500", grid_nx=60, grid_ny=127,
        )
        self.user = get_user_model().objects.create_user(nickname="빨래요정", region=region)
        self.client.force_authenticate(user=self.user)

    def test_laundry_api(self, mocked):
        mocked.return_value = make_hourly()
        response = self.client.get(reverse("situations:laundry"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["situation"], "LAUNDRY")
        for key in ("score", "summary", "overview", "recommendedTime", "recommendedMessage"):
            self.assertIn(key, response.data)

    def test_location_required(self, mocked):
        self.user.region = None
        self.user.save()
        response = self.client.get(reverse("situations:laundry"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class RecommendationConsistencyTests(SimpleTestCase):
    """알림의 옷차림·우산 기준이 홈 생활정보와 같은지 확인합니다."""

    def test_outfit_matches_home_for_normal_user(self):
        for temp in (30, 24, 21, 18, 15, 10, 6, 0):
            code, _ = get_outfit(temp)
            message = recommend_outfit(temp, PremiumProfile.ColdSensitivity.NORMAL)
            self.assertEqual(message, OUTFIT_MESSAGES[code])

    def test_cold_sensitive_user_gets_warmer_outfit(self):
        code, _ = get_outfit(15 - 2)
        message = recommend_outfit(15, PremiumProfile.ColdSensitivity.VERY_SENSITIVE)
        self.assertEqual(message, OUTFIT_MESSAGES[code])

    def test_rain_after_12_hours_is_ignored(self):
        hourly = [
            {"hour": h, "condition": "CLEAR", "precipitationProbability": 0}
            for h in range(24)
        ]
        hourly[15]["condition"] = "RAIN"
        self.assertFalse(will_rain(hourly))

def make_running_hourly(feels=15, **kwargs):
    hourly = make_hourly(start_hour=5, **kwargs)
    for item in hourly:
        item["feelsLike"] = feels
    return hourly


class RunningLogicTests(SimpleTestCase):
    def test_good_day_has_morning_and_evening(self):
        info = build_running_info(make_running_hourly(), today=TODAY)
        self.assertEqual(info["recommendedTimes"], [
            {"start": "07:00", "end": "10:00"},
            {"start": "17:00", "end": "20:00"},
        ])
        self.assertIn("최적", info["summary"])

    def test_rain_all_day(self):
        info = build_running_info(make_running_hourly(condition="RAIN"), today=TODAY)
        self.assertEqual(info["recommendedTimes"], [])
        self.assertIn("실내", info["summary"])

    def test_bad_air_blocks_running(self):
        air = {"grade": "VERY_BAD", "label": "매우나쁨", "pm10": 200, "pm25": 90, "stationName": "중구"}
        info = build_running_info(make_running_hourly(), today=TODAY, air=air)
        self.assertEqual(info["recommendedTimes"], [])
        self.assertIn("미세먼지", info["summary"])

    def test_hot_afternoon_keeps_only_morning(self):
        hourly = make_running_hourly()
        for item in hourly:
            if item["hour"] >= 12:
                item["feelsLike"] = 31
        info = build_running_info(hourly, today=TODAY)
        self.assertEqual(len(info["recommendedTimes"]), 1)
        self.assertEqual(info["recommendedTimes"][0]["start"], "07:00")


class AirGradeTests(SimpleTestCase):
    def test_pm10_grades(self):
        self.assertEqual(grade_of(25, PM10_LIMITS), "GOOD")
        self.assertEqual(grade_of(60, PM10_LIMITS), "NORMAL")
        self.assertEqual(grade_of(120, PM10_LIMITS), "BAD")
        self.assertEqual(grade_of(200, PM10_LIMITS), "VERY_BAD")

@patch("situations.views.get_uv_forecast", return_value=None)
@patch("situations.views.get_air_quality", return_value=None)
@patch("situations.views.get_hourly_weather")
class RunningAPITests(APITestCase):
    def setUp(self):
        region = Region.objects.create(
            region_code="1114055000", region_name="서울특별시 중구 소공동",
            lat="37.563800", lng="126.979500", grid_nx=60, grid_ny=127,
        )
        self.user = get_user_model().objects.create_user(nickname="러닝요정", region=region)
        self.client.force_authenticate(user=self.user)

    def test_running_api(self, mocked_hourly, *_):
        mocked_hourly.return_value = make_running_hourly()
        response = self.client.get(reverse("situations:running"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["situation"], "RUNNING")
        self.assertEqual(len(response.data["recommendedTimes"]), 2)

def make_uv_forecast(value):
    start = datetime(TODAY.year, TODAY.month, TODAY.day, 6, tzinfo=KST)
    return [{"time": start + timedelta(hours=h), "value": value} for h in range(0, 15, 3)]


class UVTests(SimpleTestCase):
    def test_grades(self):
        self.assertEqual(uv_grade(2)[0], "LOW")
        self.assertEqual(uv_grade(5)[0], "NORMAL")
        self.assertEqual(uv_grade(7)[0], "HIGH")
        self.assertEqual(uv_grade(9)[0], "VERY_HIGH")
        self.assertEqual(uv_grade(11)[0], "DANGER")

    def test_summary_uses_daytime_max(self):
        forecast = make_uv_forecast(3)
        forecast[2]["value"] = 7  # 12시
        self.assertEqual(summarize_uv(forecast, TODAY.isoformat())["value"], 7)

    def test_strong_uv_adds_sunscreen_note(self):
        info = build_running_info(make_running_hourly(), today=TODAY,
                                  uv_forecast=make_uv_forecast(9))
        self.assertEqual(info["uvIndex"]["grade"], "VERY_HIGH")
        self.assertIn("선크림", info["summary"])

class HydrationLogicTests(SimpleTestCase):
    def test_hot_day_adds_water(self):
        self.assertEqual(recommended_ml({"maxTemperature": 25}), 1500)
        self.assertEqual(recommended_ml({"maxTemperature": 31}), 2000)
        self.assertEqual(recommended_ml(None), 1500)

    def test_very_dry_message(self):
        message = intake_message({"humidity": 20, "maxTemperature": 22})
        self.assertIn("매우 건조", message)


@patch("home.services.kma_client.now_kst", return_value=FIXED_NOW)
@patch("situations.views.get_current_weather", return_value={"humidity": 20, "maxTemperature": 22})
class HydrationAPITests(APITestCase):
    def setUp(self):
        region = Region.objects.create(
            region_code="1114055000", region_name="서울특별시 중구 소공동",
            lat="37.563800", lng="126.979500", grid_nx=60, grid_ny=127,
        )
        self.user = get_user_model().objects.create_user(nickname="수분요정", region=region)
        self.client.force_authenticate(user=self.user)

    def add(self, time, amount):
        return self.client.post(reverse("situations:hydration-record-create"),
                                {"time": time, "amountMl": amount}, format="json")

    def test_empty_day(self, *_):
        response = self.client.get(reverse("situations:hydration"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["currentMl"], 0)
        self.assertEqual(len(response.data["hourly"]), 24)
        self.assertIn("매우 건조", response.data["message"])

    def test_add_records_updates_summary(self, *_):
        self.add("09:00", 180)
        response = self.add("21:00", 420)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["currentMl"], 600)
        self.assertEqual(response.data["percent"], 40)
        self.assertEqual(response.data["hourly"][9]["amountMl"], 180)

    def test_only_half_hour_steps(self, *_):
        self.assertEqual(self.add("09:15", 180).status_code, status.HTTP_400_BAD_REQUEST)

    def test_future_time_rejected(self, *_):
        self.assertEqual(self.add("21:30", 180).status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_delete_others_record(self, *_):
        other = get_user_model().objects.create_user(nickname="다른사람")
        record = WaterIntake.objects.create(user=other, drank_at=FIXED_NOW, amount_ml=100)
        response = self.client.delete(
            reverse("situations:hydration-record-delete", args=[record.pk])
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_works_without_location(self, *_):
        self.user.region = None
        self.user.save()
        response = self.client.get(reverse("situations:hydration"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["humidity"])