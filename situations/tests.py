import requests
from io import StringIO
from uuid import uuid4
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from situations.services.liner_client import generate_notification_copy

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Region
from situations.services.laundry import build_laundry_info

from home.services.life_info import get_outfit
from premium.models import NotificationPreference, PremiumEntitlement, PremiumProfile
from situations.services.notification_recommendations import (
    build_laundry_message,
    build_outerwear_message,
    build_umbrella_message,
)
from situations.services.recommendations import (
    OUTFIT_MESSAGES,
    recommend_outfit,
    will_rain,
)
from situations.services.scheduler import (
    send_daily_preference_notifications,
    send_due_outing_notifications,
)

from situations.services.airkorea import PM10_LIMITS, grade_of
from situations.services.running import build_running_info
from situations.services.uv import summarize_uv, uv_grade

from situations.models import (
    NotificationLog,
    NotificationSchedule,
    WaterIntake,
)
from situations.services.hydration import intake_message, recommended_ml
from situations.services.delivery import deliver_notification
from situations.services.onesignal import send_push_to_user


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


class OneSignalClientTests(SimpleTestCase):
    @override_settings(
        ONESIGNAL_APP_ID="test-app-id",
        ONESIGNAL_REST_API_KEY="test-api-key",
        ONESIGNAL_API_URL="https://onesignal.example/notifications",
        ONESIGNAL_DRY_RUN=False,
    )
    @patch("situations.services.onesignal.requests.post")
    def test_sends_provider_idempotency_key(self, mocked_post):
        provider_key = str(uuid4())
        mocked_response = mocked_post.return_value
        mocked_response.raise_for_status.return_value = None
        mocked_response.json.return_value = {"id": "message-id"}

        result = send_push_to_user(
            user_id=7,
            title="알림 제목",
            message="알림 내용",
            idempotency_key=provider_key,
        )

        self.assertEqual(result, {"id": "message-id"})
        request_kwargs = mocked_post.call_args.kwargs
        self.assertEqual(
            request_kwargs["json"]["idempotency_key"],
            provider_key,
        )
        self.assertEqual(
            request_kwargs["json"]["include_aliases"]["external_id"],
            ["7"],
        )
        self.assertEqual(request_kwargs["timeout"], 10)

    @override_settings(
        ONESIGNAL_APP_ID="test-app-id",
        ONESIGNAL_REST_API_KEY="test-api-key",
        ONESIGNAL_DRY_RUN=True,
    )
    @patch("situations.services.onesignal.requests.post")
    def test_dry_run_does_not_call_onesignal(self, mocked_post):
        provider_key = str(uuid4())

        result = send_push_to_user(
            user_id=7,
            title="알림 제목",
            message="알림 내용",
            idempotency_key=provider_key,
        )

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["idempotency_key"], provider_key)
        mocked_post.assert_not_called()

    @override_settings(
        ONESIGNAL_APP_ID="test-app-id",
        ONESIGNAL_REST_API_KEY="test-api-key",
        ONESIGNAL_DRY_RUN=False,
    )
    def test_rejects_non_uuid_idempotency_key(self):
        with self.assertRaisesMessage(ValueError, "UUID 형식"):
            send_push_to_user(
                user_id=7,
                title="알림 제목",
                message="알림 내용",
                idempotency_key="not-a-uuid",
            )

    @override_settings(
        ONESIGNAL_APP_ID="test-app-id",
        ONESIGNAL_REST_API_KEY="test-api-key",
        ONESIGNAL_DRY_RUN=False,
    )
    @patch(
        "situations.services.onesignal.requests.post",
        side_effect=requests.Timeout,
    )
    def test_network_failure_raises_runtime_error(self, mocked_post):
        with self.assertRaisesMessage(RuntimeError, "발송에 실패"):
            send_push_to_user(
                user_id=7,
                title="알림 제목",
                message="알림 내용",
                idempotency_key=str(uuid4()),
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


class NotificationScheduleAPITests(APITestCase):
    def setUp(self):
        self.region = Region.objects.create(
            region_code="1111053000",
            region_name="서울특별시 종로구 사직동",
            lat="37.575000",
            lng="126.970000",
            grid_nx=60,
            grid_ny=127,
        )
        self.user = get_user_model().objects.create_user(
            nickname="일정사용자",
        )
        self.other_user = get_user_model().objects.create_user(
            nickname="다른일정사용자",
        )
        self.client.force_authenticate(user=self.user)

    def create_schedule(self, *, user=None, name="학원 갈 때"):
        return NotificationSchedule.objects.create(
            user=user or self.user,
            name=name,
            purpose=NotificationSchedule.Purpose.ACADEMY,
            weekdays=[0, 4],
            outing_time=time(18, 0),
            region=self.region,
            lead_minutes=NotificationSchedule.LeadMinutes.ONE_HOUR,
        )

    def test_list_returns_only_authenticated_users_schedules(self):
        own_schedule = self.create_schedule()
        self.create_schedule(user=self.other_user, name="다른 사용자 일정")

        response = self.client.get(
            reverse("situations:schedule-list-create")
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["scheduleId"], own_schedule.pk)

    def test_create_saves_authenticated_user_and_sorts_weekdays(self):
        response = self.client.post(
            reverse("situations:schedule-list-create"),
            {
                "name": "출근할 때",
                "purpose": NotificationSchedule.Purpose.COMMUTE,
                "weekdays": [4, 0, 2],
                "outingTime": "08:30",
                "regionCode": self.region.region_code,
                "leadMinutes": 30,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        schedule = NotificationSchedule.objects.get(
            pk=response.data["scheduleId"]
        )
        self.assertEqual(schedule.user, self.user)
        self.assertEqual(schedule.weekdays, [0, 2, 4])

    def test_patch_updates_schedule(self):
        schedule = self.create_schedule()

        response = self.client.patch(
            reverse("situations:schedule-detail", args=[schedule.pk]),
            {
                "name": "수정된 일정",
                "weekdays": [2],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        schedule.refresh_from_db()
        self.assertEqual(schedule.name, "수정된 일정")
        self.assertEqual(schedule.weekdays, [2])

    def test_delete_removes_schedule(self):
        schedule = self.create_schedule()

        response = self.client.delete(
            reverse("situations:schedule-detail", args=[schedule.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            NotificationSchedule.objects.filter(pk=schedule.pk).exists()
        )

    def test_cannot_access_another_users_schedule(self):
        schedule = self.create_schedule(user=self.other_user)
        url = reverse("situations:schedule-detail", args=[schedule.pk])

        self.assertEqual(
            self.client.get(url).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.patch(url, {"name": "탈취"}, format="json").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.delete(url).status_code,
            status.HTTP_404_NOT_FOUND,
        )


class UmbrellaNotificationMessageTests(SimpleTestCase):
    def setUp(self):
        self.clear_forecast = [
            {
                "hour": 18,
                "condition": "CLEAR",
                "precipitationProbability": 0,
            }
        ]
        self.rain_forecast = [
            {
                "hour": 18,
                "condition": "RAIN",
                "precipitationProbability": 80,
            }
        ]

    def test_skips_notification_when_rain_is_not_expected(self):
        result = build_umbrella_message(
            schedule_name="학원",
            hourly_weather=self.clear_forecast,
        )

        self.assertIsNone(result)

    def test_rain_forecast_creates_umbrella_only_message(self):
        title, body = build_umbrella_message(
            schedule_name="학원",
            hourly_weather=self.rain_forecast,
        )

        self.assertIn("우산", title)
        self.assertIn("우산", body)
        self.assertNotIn("체감온도", body)


class DailyRecommendationMessageTests(SimpleTestCase):
    def test_outerwear_message_uses_temperature_and_user_sensitivity(self):
        profile = PremiumProfile(
            cold_sensitivity=PremiumProfile.ColdSensitivity.VERY_SENSITIVE,
        )

        title, body = build_outerwear_message(
            profile=profile,
            current_weather={"feelsLike": 12},
        )

        self.assertIn("옷차림", title)
        self.assertIn("체감온도는 12.0℃", body)
        self.assertIn("트렌치코트", body)

    def test_laundry_combines_all_matching_selected_conditions(self):
        profile = PremiumProfile(
            laundry_rain_alert=True,
            laundry_humidity_alert=True,
            laundry_indoor_tip=True,
        )

        title, body = build_laundry_message(
            profile=profile,
            current_weather={"humidity": 80},
            hourly_weather=[
                {
                    "hour": 10,
                    "condition": "RAIN",
                    "precipitationProbability": 80,
                }
            ],
        )

        self.assertIn("비", title)
        self.assertIn("비 예보", body)
        self.assertIn("습도는 80%", body)
        self.assertIn("제습기", body)

    def test_daily_laundry_summary_reports_good_weather(self):
        title, body = build_laundry_message(
            profile=PremiumProfile(),
            current_weather={"humidity": 45},
            hourly_weather=[
                {
                    "hour": 10,
                    "condition": "CLEAR",
                    "precipitationProbability": 0,
                }
            ],
        )

        self.assertEqual(title, "오늘은 빨래하기 좋아요")
        self.assertIn("습도는 45%", body)

    def test_daily_laundry_summary_reports_bad_weather(self):
        title, body = build_laundry_message(
            profile=PremiumProfile(),
            current_weather={"humidity": 80},
            hourly_weather=[
                {
                    "hour": 10,
                    "condition": "RAIN",
                    "precipitationProbability": 80,
                }
            ],
        )

        self.assertEqual(title, "오늘은 실외 빨래를 피해주세요")
        self.assertIn("비 예보", body)


class NotificationDeliveryTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            nickname="발송사용자",
        )

    def deliver(self, *, dedupe_key="exercise:1:2026-10-10"):
        return deliver_notification(
            user=self.user,
            notification_type=NotificationLog.NotificationType.EXERCISE,
            target_date=TODAY,
            dedupe_key=dedupe_key,
            title="운동 알림",
            message="오늘도 가볍게 움직여 보세요.",
        )

    @override_settings(ONESIGNAL_DRY_RUN=False)
    @patch(
        "situations.services.delivery.send_push_to_user",
        return_value={"id": "provider-message-id"},
    )
    def test_sent_notification_is_not_delivered_twice(self, mocked_send):
        first_log = self.deliver()
        second_log = self.deliver()

        self.assertEqual(first_log.pk, second_log.pk)
        self.assertEqual(second_log.status, NotificationLog.Status.SENT)
        self.assertEqual(second_log.attempt_count, 1)
        mocked_send.assert_called_once()

    @override_settings(ONESIGNAL_DRY_RUN=False)
    @patch("situations.services.delivery.send_push_to_user")
    def test_failed_notification_retries_with_same_provider_key(
        self,
        mocked_send,
    ):
        mocked_send.side_effect = [
            RuntimeError("일시적인 발송 실패"),
            {"id": "provider-message-id"},
        ]

        first_log = self.deliver()
        first_provider_key = str(first_log.provider_idempotency_key)
        second_log = self.deliver()

        self.assertEqual(first_log.status, NotificationLog.Status.FAILED)
        self.assertEqual(second_log.status, NotificationLog.Status.SENT)
        self.assertEqual(second_log.attempt_count, 2)
        self.assertEqual(mocked_send.call_count, 2)
        self.assertEqual(
            mocked_send.call_args_list[0].kwargs["idempotency_key"],
            first_provider_key,
        )
        self.assertEqual(
            mocked_send.call_args_list[1].kwargs["idempotency_key"],
            first_provider_key,
        )

    @override_settings(ONESIGNAL_DRY_RUN=True)
    @patch(
        "situations.services.delivery.send_push_to_user",
        return_value={"dry_run": True},
    )
    def test_dry_run_is_recorded_as_skipped(self, mocked_send):
        log = self.deliver()

        self.assertEqual(log.status, NotificationLog.Status.SKIPPED)
        self.assertIn("Dry-run", log.error_message)
        mocked_send.assert_called_once()


class DailyNotificationPreferenceSchedulerTests(APITestCase):
    def setUp(self):
        region = Region.objects.create(
            region_code="1111053000",
            region_name="서울특별시 종로구 사직동",
            lat="37.575000",
            lng="126.970000",
            grid_nx=60,
            grid_ny=127,
        )
        self.user = get_user_model().objects.create_user(
            nickname="알림스케줄러사용자",
            region=region,
        )
        PremiumProfile.objects.create(
            user=self.user,
            cold_sensitivity=PremiumProfile.ColdSensitivity.NORMAL,
            exercise_preference=PremiumProfile.ExercisePreference.MORNING,
            survey_completed_at=FIXED_NOW,
        )
        PremiumEntitlement.objects.create(
            user=self.user,
            started_at=FIXED_NOW - timedelta(days=1),
            expires_at=FIXED_NOW + timedelta(days=20),
        )

    @override_settings(
        EXERCISE_MORNING_NOTIFICATION_HOUR=7,
        WEATHER_NOTIFICATION_WINDOW_MINUTES=10,
        LINER_ENABLED=False,
    )
    @patch("situations.services.scheduler.deliver_notification")
    @patch("situations.services.scheduler.get_hourly_weather")
    @patch("situations.services.scheduler.get_current_weather")
    def test_disabled_exercise_setting_prevents_delivery(
        self,
        mocked_current,
        mocked_hourly,
        mocked_delivery,
    ):
        NotificationPreference.objects.create(
            user=self.user,
            exercise_enabled=False,
        )

        result = send_daily_preference_notifications(
            now=datetime(2026, 10, 10, 7, 0, tzinfo=KST),
        )

        self.assertEqual(result["exercise_processed"], 0)
        mocked_current.assert_not_called()
        mocked_hourly.assert_not_called()
        mocked_delivery.assert_not_called()

    @override_settings(
        EXERCISE_MORNING_NOTIFICATION_HOUR=7,
        WEATHER_NOTIFICATION_WINDOW_MINUTES=10,
        LINER_ENABLED=False,
    )
    @patch("situations.services.scheduler.deliver_notification")
    @patch(
        "situations.services.scheduler.get_hourly_weather",
        return_value=[
            {
                "hour": 8,
                "condition": "CLEAR",
                "precipitationProbability": 0,
            }
        ],
    )
    @patch(
        "situations.services.scheduler.get_current_weather",
        return_value={"feelsLike": 20, "windSpeed": 1},
    )
    def test_enabled_exercise_setting_allows_delivery(
        self,
        mocked_current,
        mocked_hourly,
        mocked_delivery,
    ):
        mocked_delivery.return_value.status = NotificationLog.Status.SENT
        NotificationPreference.objects.create(
            user=self.user,
            exercise_enabled=True,
        )

        result = send_daily_preference_notifications(
            now=datetime(2026, 10, 10, 7, 0, tzinfo=KST),
        )

        self.assertEqual(result["exercise_processed"], 1)
        mocked_current.assert_called_once()
        mocked_hourly.assert_called_once()
        mocked_delivery.assert_called_once()

    @override_settings(
        EXERCISE_FLEXIBLE_NOTIFICATION_HOUR=18,
        WEATHER_NOTIFICATION_WINDOW_MINUTES=10,
        LINER_ENABLED=False,
    )
    @patch("situations.services.scheduler.deliver_notification")
    @patch(
        "situations.services.scheduler.get_hourly_weather",
        return_value=[
            {
                "hour": 19,
                "condition": "CLEAR",
                "precipitationProbability": 0,
            }
        ],
    )
    @patch(
        "situations.services.scheduler.get_current_weather",
        return_value={"feelsLike": 20, "windSpeed": 1},
    )
    def test_flexible_exercise_setting_uses_default_notification_hour(
        self,
        mocked_current,
        mocked_hourly,
        mocked_delivery,
    ):
        mocked_delivery.return_value.status = NotificationLog.Status.SENT
        profile = self.user.premium_profile
        profile.exercise_preference = PremiumProfile.ExercisePreference.FLEXIBLE
        profile.save(update_fields=["exercise_preference"])
        NotificationPreference.objects.create(
            user=self.user,
            exercise_enabled=True,
        )

        result = send_daily_preference_notifications(
            now=datetime(2026, 10, 10, 18, 0, tzinfo=KST),
        )

        self.assertEqual(result["exercise_processed"], 1)
        mocked_current.assert_called_once()
        mocked_hourly.assert_called_once()
        mocked_delivery.assert_called_once()

    @override_settings(
        OUTERWEAR_NOTIFICATION_HOUR=7,
        WEATHER_NOTIFICATION_WINDOW_MINUTES=10,
        LINER_ENABLED=False,
    )
    @patch("situations.services.scheduler.deliver_notification")
    @patch(
        "situations.services.scheduler.get_hourly_weather",
        return_value=[],
    )
    @patch(
        "situations.services.scheduler.get_current_weather",
        return_value={"feelsLike": 12},
    )
    def test_outerwear_is_sent_daily_without_an_outing_schedule(
        self,
        mocked_current,
        mocked_hourly,
        mocked_delivery,
    ):
        mocked_delivery.return_value.status = NotificationLog.Status.SENT
        NotificationPreference.objects.create(
            user=self.user,
            outerwear_enabled=True,
        )

        result = send_daily_preference_notifications(
            now=datetime(2026, 10, 10, 7, 0, tzinfo=KST),
        )

        self.assertEqual(result["outerwear_processed"], 1)
        mocked_current.assert_called_once()
        mocked_hourly.assert_called_once()
        mocked_delivery.assert_called_once()
        self.assertEqual(
            mocked_delivery.call_args.kwargs["notification_type"],
            NotificationLog.NotificationType.OUTERWEAR,
        )

    @override_settings(
        LAUNDRY_NOTIFICATION_HOUR=7,
        WEATHER_NOTIFICATION_WINDOW_MINUTES=10,
        LINER_ENABLED=False,
    )
    @patch("situations.services.scheduler.deliver_notification")
    @patch(
        "situations.services.scheduler.get_hourly_weather",
        return_value=[],
    )
    @patch(
        "situations.services.scheduler.get_current_weather",
        return_value={"humidity": 45},
    )
    def test_daily_laundry_summary_is_sent_every_day(
        self,
        mocked_current,
        mocked_hourly,
        mocked_delivery,
    ):
        mocked_delivery.return_value.status = NotificationLog.Status.SENT
        NotificationPreference.objects.create(
            user=self.user,
            laundry_enabled=True,
        )

        result = send_daily_preference_notifications(
            now=datetime(2026, 10, 10, 7, 0, tzinfo=KST),
        )

        self.assertEqual(result["laundry_processed"], 1)
        mocked_delivery.assert_called_once()
        self.assertIn(
            "빨래하기 좋아요",
            mocked_delivery.call_args.kwargs["title"],
        )

    @override_settings(
        EXERCISE_MORNING_NOTIFICATION_HOUR=7,
        WEATHER_NOTIFICATION_WINDOW_MINUTES=10,
        LINER_ENABLED=False,
    )
    @patch("situations.services.scheduler.deliver_notification")
    @patch(
        "situations.services.scheduler.get_hourly_weather",
        return_value=[],
    )
    @patch(
        "situations.services.scheduler.get_current_weather",
        return_value={"feelsLike": 20, "windSpeed": 1},
    )
    def test_failed_delivery_is_not_counted_as_processed(
        self,
        mocked_current,
        mocked_hourly,
        mocked_delivery,
    ):
        mocked_delivery.return_value.status = NotificationLog.Status.FAILED
        NotificationPreference.objects.create(
            user=self.user,
            exercise_enabled=True,
        )

        result = send_daily_preference_notifications(
            now=datetime(2026, 10, 10, 7, 0, tzinfo=KST),
        )

        self.assertEqual(result["exercise_processed"], 0)
        self.assertEqual(result["errors"], 1)


class UmbrellaScheduleDeliveryTests(APITestCase):
    def setUp(self):
        self.region = Region.objects.create(
            region_code="1111054000",
            region_name="서울특별시 종로구 삼청동",
            lat="37.584000",
            lng="126.982000",
            grid_nx=60,
            grid_ny=127,
        )
        self.user = get_user_model().objects.create_user(
            nickname="우산일정사용자",
            region=self.region,
        )

    @override_settings(
        WEATHER_NOTIFICATION_WINDOW_MINUTES=10,
        LINER_ENABLED=False,
        FRONTEND_BASE_URL="https://example.com",
    )
    @patch("situations.services.scheduler.deliver_notification")
    @patch(
        "situations.services.scheduler.get_hourly_weather",
        return_value=[
            {
                "time": "2026-10-10T08:00:00+09:00",
                "hour": 8,
                "condition": "RAIN",
                "precipitationProbability": 80,
                "feelsLike": 12,
            }
        ],
    )
    @patch(
        "situations.services.scheduler.get_current_weather",
        return_value={},
    )
    def test_existing_schedule_sends_umbrella_without_global_switch(
        self,
        mocked_current,
        mocked_hourly,
        mocked_delivery,
    ):
        mocked_delivery.return_value.status = NotificationLog.Status.SENT
        PremiumProfile.objects.create(
            user=self.user,
            cold_sensitivity=PremiumProfile.ColdSensitivity.NORMAL,
        )
        NotificationPreference.objects.create(
            user=self.user,
            outerwear_enabled=True,
        )
        NotificationSchedule.objects.create(
            user=self.user,
            name="학원 갈 때",
            purpose=NotificationSchedule.Purpose.ACADEMY,
            weekdays=[5],
            outing_time=time(8, 0),
            region=self.region,
            lead_minutes=NotificationSchedule.LeadMinutes.ONE_HOUR,
        )

        result = send_due_outing_notifications(
            now=datetime(2026, 10, 10, 7, 0, tzinfo=KST),
        )

        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["due"], 1)
        self.assertEqual(result["processed"], 1)
        mocked_current.assert_not_called()
        mocked_hourly.assert_called_once()
        mocked_delivery.assert_called_once()
        self.assertIn(
            "우산",
            mocked_delivery.call_args.kwargs["message"],
        )
        self.assertNotIn(
            "체감온도",
            mocked_delivery.call_args.kwargs["message"],
        )

    @override_settings(WEATHER_NOTIFICATION_WINDOW_MINUTES=10)
    @patch("situations.services.scheduler.get_current_weather")
    def test_no_schedule_means_no_umbrella_delivery(self, mocked_current):
        result = send_due_outing_notifications(
            now=datetime(2026, 10, 10, 7, 0, tzinfo=KST),
        )

        self.assertEqual(result["checked"], 0)
        self.assertEqual(result["processed"], 0)
        mocked_current.assert_not_called()


class SendWeatherNotificationsCommandTests(SimpleTestCase):
    outing_result = {
        "checked": 1,
        "due": 1,
        "processed": 1,
        "skipped": 0,
        "errors": 0,
    }
    preference_result = {
        "checked": 1,
        "outerwear_processed": 1,
        "exercise_processed": 0,
        "laundry_processed": 1,
        "skipped": 0,
        "errors": 0,
    }

    @patch(
        "situations.management.commands.send_weather_notifications."
        "send_daily_preference_notifications"
    )
    @patch(
        "situations.management.commands.send_weather_notifications."
        "send_due_outing_notifications"
    )
    def test_command_runs_both_notification_schedulers(
        self,
        mocked_outing,
        mocked_preference,
    ):
        mocked_outing.return_value = self.outing_result
        mocked_preference.return_value = self.preference_result
        stdout = StringIO()

        call_command(
            "send_weather_notifications",
            now="2026-10-10T07:00:00+09:00",
            stdout=stdout,
        )

        mocked_outing.assert_called_once()
        mocked_preference.assert_called_once()
        self.assertIn("맞춤 날씨 알림 처리가 완료되었습니다.", stdout.getvalue())

    @patch(
        "situations.management.commands.send_weather_notifications."
        "send_daily_preference_notifications"
    )
    @patch(
        "situations.management.commands.send_weather_notifications."
        "send_due_outing_notifications"
    )
    def test_command_fails_when_delivery_has_errors(
        self,
        mocked_outing,
        mocked_preference,
    ):
        mocked_outing.return_value = {
            **self.outing_result,
            "errors": 1,
        }
        mocked_preference.return_value = self.preference_result

        with self.assertRaises(CommandError):
            call_command(
                "send_weather_notifications",
                now="2026-10-10T07:00:00+09:00",
            )


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
