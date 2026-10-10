from django.test import TestCase

# Create your tests here.
# accounts/tests.py
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Region
from accounts.models import SocialAccount

User = get_user_model()


class OnboardingAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(nickname="user_a1b2c3d4")
        self.client.force_authenticate(user=self.user)
        self.region = Region.objects.create(
            region_code="1114055000",
            region_name="서울특별시 중구 소공동",
            lat="37.563800", lng="126.979500",
            grid_nx=60, grid_ny=127,
        )

    def test_set_location_by_gps(self):
        response = self.client.patch(
            reverse("me-location"),
            {"locationMode": "GPS", "lat": 37.56653912, "lng": 126.97796919},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["region"]["regionCode"], "1114055000")

    def test_set_location_manually(self):
        response = self.client.patch(
            reverse("me-location"),
            {"locationMode": "MANUAL", "regionCode": "1114055000"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["locationMode"], "MANUAL")

    def test_gps_outside_korea_is_rejected(self):
        response = self.client.patch(
            reverse("me-location"),
            {"locationMode": "GPS", "lat": 40.7128, "lng": -74.0060},  # 뉴욕
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_required(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse("me"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_shows_social_email_as_read_only_login_account(self):
        SocialAccount.objects.create(
            user=self.user,
            provider=SocialAccount.Provider.KAKAO,
            provider_uid="kakao-test-user",
            email="likelion@daum.net",
        )

        response = self.client.get(reverse("me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["loginAccount"],
            {
                "provider": "KAKAO",
                "email": "likelion@daum.net",
                "displayId": "likelion@daum.net",
            },
        )

    def test_me_uses_provider_label_when_social_email_is_missing(self):
        SocialAccount.objects.create(
            user=self.user,
            provider=SocialAccount.Provider.KAKAO,
            provider_uid="kakao-no-email-user",
            email=None,
        )

        response = self.client.get(reverse("me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["loginAccount"]["displayId"],
            "카카오 계정",
        )

    def test_set_nickname(self):
        response = self.client.patch(reverse("me-nickname"), {"nickname": "날씨요정"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["isNicknameSet"])

    def test_nickname_too_long_is_rejected(self):
        response = self.client.patch(reverse("me-nickname"), {"nickname": "가" * 11}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_nickname_is_rejected(self):
        User.objects.create_user(nickname="날씨요정")
        response = self.client.patch(reverse("me-nickname"), {"nickname": "날씨요정"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_onboarding_completes_after_nickname_and_location(self):
        self.client.patch(
            reverse("me-location"),
            {"locationMode": "GPS", "lat": 37.5665, "lng": 126.9780},
            format="json",
        )
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_onboarded)  # 닉네임이 아직 임시값

        response = self.client.patch(reverse("me-nickname"), {"nickname": "날씨요정"}, format="json")
        self.assertTrue(response.data["isOnboarded"])
