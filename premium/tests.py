from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import NotificationPreference, PremiumProfile


User = get_user_model()


class PremiumProfileAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(nickname="프리미엄사용자")
        self.client.force_authenticate(user=self.user)
        self.url = reverse("premium:profile")

    def test_login_is_required(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_returns_default_incomplete_profile(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["coldSensitivity"], "UNKNOWN")
        self.assertEqual(response.data["exercisePreference"], "FLEXIBLE")
        self.assertEqual(
            response.data["laundryPreferences"],
            ["DAILY_SUMMARY"],
        )
        self.assertFalse(response.data["isCompleted"])
        self.assertIsNone(response.data["surveyCompletedAt"])
        self.assertTrue(PremiumProfile.objects.filter(user=self.user).exists())

    def test_put_saves_all_personalization_preferences(self):
        response = self.client.put(
            self.url,
            {
                "coldSensitivity": "VERY_SENSITIVE",
                "exercisePreference": "MORNING",
                "laundryPreferences": ["RAIN_BEFORE", "INDOOR_DRYING_TIP"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["isCompleted"])
        self.assertIsNotNone(response.data["surveyCompletedAt"])

        profile = PremiumProfile.objects.get(user=self.user)
        self.assertEqual(
            profile.cold_sensitivity,
            PremiumProfile.ColdSensitivity.VERY_SENSITIVE,
        )
        self.assertEqual(
            profile.exercise_preference,
            PremiumProfile.ExercisePreference.MORNING,
        )
        self.assertTrue(profile.laundry_rain_alert)
        self.assertFalse(profile.laundry_humidity_alert)
        self.assertTrue(profile.laundry_indoor_tip)

    def test_put_requires_all_personalization_categories(self):
        response = self.client.put(
            self.url,
            {"coldSensitivity": "NORMAL"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("exercisePreference", response.data)
        self.assertIn("laundryPreferences", response.data)

    def test_laundry_preferences_cannot_contain_duplicates(self):
        response = self.client.put(
            self.url,
            {
                "coldSensitivity": "NORMAL",
                "exercisePreference": "EVENING",
                "laundryPreferences": ["HIGH_HUMIDITY", "HIGH_HUMIDITY"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("laundryPreferences", response.data)

    def test_daily_summary_laundry_preference_must_be_selected_alone(self):
        response = self.client.put(
            self.url,
            {
                "coldSensitivity": "NORMAL",
                "exercisePreference": "EVENING",
                "laundryPreferences": ["DAILY_SUMMARY", "RAIN_BEFORE"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("laundryPreferences", response.data)

    def test_legacy_no_notification_value_is_rejected(self):
        response = self.client.put(
            self.url,
            {
                "coldSensitivity": "NORMAL",
                "exercisePreference": "NO_NOTIFICATION",
                "laundryPreferences": ["DAILY_SUMMARY"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("exercisePreference", response.data)

    def test_patch_preserves_omitted_preferences_and_completion_time(self):
        PremiumProfile.objects.create(
            user=self.user,
            cold_sensitivity=PremiumProfile.ColdSensitivity.NORMAL,
            exercise_preference=PremiumProfile.ExercisePreference.MORNING,
            laundry_rain_alert=True,
        )
        self.client.put(
            self.url,
            {
                "coldSensitivity": "NORMAL",
                "exercisePreference": "MORNING",
                "laundryPreferences": ["RAIN_BEFORE"],
            },
            format="json",
        )
        profile = PremiumProfile.objects.get(user=self.user)
        completed_at = profile.survey_completed_at

        response = self.client.patch(
            self.url,
            {"exercisePreference": "EVENING"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile.refresh_from_db()
        self.assertEqual(
            profile.exercise_preference,
            PremiumProfile.ExercisePreference.EVENING,
        )
        self.assertEqual(
            profile.cold_sensitivity,
            PremiumProfile.ColdSensitivity.NORMAL,
        )
        self.assertTrue(profile.laundry_rain_alert)
        self.assertEqual(profile.survey_completed_at, completed_at)

    def test_partial_draft_does_not_mark_survey_as_completed(self):
        response = self.client.patch(
            self.url,
            {"coldSensitivity": "HEAT_SENSITIVE"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["isCompleted"])
        self.assertIsNone(response.data["surveyCompletedAt"])


class NotificationPreferenceAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(nickname="알림설정사용자")
        self.client.force_authenticate(user=self.user)
        self.url = reverse("premium:notification-settings")

    def test_login_is_required(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_returns_opt_in_defaults(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "outerwearEnabled": False,
                "exerciseEnabled": False,
                "laundryEnabled": False,
            },
        )
        self.assertTrue(
            NotificationPreference.objects.filter(user=self.user).exists()
        )

    def test_put_requires_and_updates_all_settings(self):
        incomplete_response = self.client.put(
            self.url,
            {"exerciseEnabled": True},
            format="json",
        )

        self.assertEqual(
            incomplete_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        response = self.client.put(
            self.url,
            {
                "outerwearEnabled": True,
                "exerciseEnabled": True,
                "laundryEnabled": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        preference = NotificationPreference.objects.get(user=self.user)
        self.assertTrue(preference.outerwear_enabled)
        self.assertTrue(preference.exercise_enabled)
        self.assertFalse(preference.laundry_enabled)

    def test_patch_updates_only_the_requested_setting(self):
        NotificationPreference.objects.create(
            user=self.user,
            outerwear_enabled=True,
            laundry_enabled=True,
        )

        response = self.client.patch(
            self.url,
            {"exerciseEnabled": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "outerwearEnabled": True,
                "exerciseEnabled": True,
                "laundryEnabled": True,
            },
        )
