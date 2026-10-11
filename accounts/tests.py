from django.test import TestCase

# Create your tests here.
# accounts/tests.py
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Region
from unittest.mock import patch
from django.test import override_settings
from .models import SocialAccount

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

class WithdrawAPITests(APITestCase):
    def setUp(self):
        from fortune.models import FortuneProduct, FortunePurchase

        self.user = User.objects.create_user(nickname="탈퇴할사용자")
        SocialAccount.objects.create(
            user=self.user, provider=SocialAccount.Provider.KAKAO, provider_uid="12345",
        )
        product = FortuneProduct.objects.create(
            product_code="WITHDRAW_TEST", title="테스트 상품", price=990, duration_days=1,
        )
        self.purchase = FortunePurchase.objects.create(
            user=self.user, product=product, product_title=product.title,
            duration_days=1, amount=990, calendar_type="SOLAR",
            birth_date="2002-05-17", converted_solar_date="2002-05-17",
            birth_time_unknown=True,
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse("me")

    @override_settings(KAKAO_ADMIN_KEY="test-admin-key")
    @patch("accounts.services.requests.post")
    def test_withdraw_deletes_user_and_keeps_purchase(self, mock_post):
        mock_post.return_value.status_code = 200

        res = self.client.delete(self.url)

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(SocialAccount.objects.filter(provider_uid="12345").exists())
        self.purchase.refresh_from_db()
        self.assertIsNone(self.purchase.user)
        self.assertEqual(mock_post.call_args.kwargs["data"]["target_id"], "12345")

    @override_settings(KAKAO_ADMIN_KEY="test-admin-key")
    @patch("accounts.services.requests.post")
    def test_withdraw_continues_when_kakao_fails(self, mock_post):
        mock_post.return_value.status_code = 401

        res = self.client.delete(self.url)

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())