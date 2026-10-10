from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Region
from fortune.models import (
    FortuneProduct,
    FortuneProfile,
    FortunePurchase,
    FortuneResult,
)


class MyPageFortuneProfileAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            nickname="mypage-fortune-user"
        )
        self.client.force_authenticate(self.user)
        self.profile = FortuneProfile.objects.create(
            user=self.user,
            calendar_type=FortuneProfile.CalendarType.SOLAR,
            birth_date="2002-05-17",
            converted_solar_date="2002-05-17",
            birth_time=None,
            birth_time_unknown=True,
        )

    def update_profile(self):
        return self.client.put(
            reverse("mypage-fortune-profile"),
            {
                "calendar_type": "SOLAR",
                "birth_date": "2001-04-03",
                "birth_time": None,
                "birth_time_unknown": True,
            },
            format="json",
        )

    def test_profile_can_be_retrieved_from_mypage(self):
        response = self.client.get(reverse("mypage-fortune-profile"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["birth_date"], "2002-05-17")

    def test_update_reuses_one_profile_and_refreshes_free_result(self):
        today = timezone.localdate()
        FortuneResult.objects.create(
            user=self.user,
            target_date=today,
            title="기존 운세",
            lucky_color="파랑",
            lucky_item="우산",
            lucky_place="서점",
            detail_text="기존 상세 풀이",
        )

        response = self.update_profile()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(FortuneProfile.objects.filter(user=self.user).count(), 1)
        self.profile.refresh_from_db()
        self.assertEqual(str(self.profile.birth_date), "2001-04-03")
        self.assertFalse(
            FortuneResult.objects.filter(
                user=self.user,
                target_date=today,
            ).exists()
        )

    def test_update_keeps_active_purchase_snapshot_and_result(self):
        product = FortuneProduct.objects.create(
            product_code="MYPAGE_TEST_7D",
            title="오늘의 운세 7일",
            description="7일 동안 상세 풀이를 확인해요.",
            price=5900,
            duration_days=7,
        )
        today = timezone.localdate()
        purchase = FortunePurchase.objects.create(
            user=self.user,
            product=product,
            product_title=product.title,
            duration_days=product.duration_days,
            amount=product.price,
            calendar_type=self.profile.calendar_type,
            birth_date=self.profile.birth_date,
            converted_solar_date=self.profile.converted_solar_date,
            birth_time=self.profile.birth_time,
            birth_time_unknown=self.profile.birth_time_unknown,
            payment_status=FortunePurchase.PaymentStatus.PAID,
            active_from=today,
            active_until=today + timedelta(days=6),
            purchased_at=timezone.now(),
        )
        result = FortuneResult.objects.create(
            user=self.user,
            target_date=today,
            title="구매 당시 운세",
            lucky_color="파랑",
            lucky_item="우산",
            lucky_place="서점",
            detail_text="구매 당시 상세 풀이",
        )

        response = self.update_profile()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        purchase.refresh_from_db()
        self.assertEqual(str(purchase.birth_date), "2002-05-17")
        self.assertTrue(FortuneResult.objects.filter(id=result.id).exists())

    def test_update_requires_an_existing_profile(self):
        self.profile.delete()

        response = self.update_profile()

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["code"], "FORTUNE_PROFILE_NOT_FOUND")


class MyPageSummaryAPITests(APITestCase):
    def setUp(self):
        self.region = Region.objects.create(
            region_code="1141058500",
            region_name="서울특별시 서대문구 신촌동",
            lat="37.556000",
            lng="126.936000",
            grid_nx=59,
            grid_ny=126,
        )
        self.user = get_user_model().objects.create_user(
            nickname="마이페이지사용자",
            region=self.region,
        )

    def test_login_is_required(self):
        response = self.client.get(
            reverse("mypage-summary")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_summary_contains_profile_and_notifications(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(
            reverse("mypage-summary")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["profile"]["nickname"],
            self.user.nickname,
        )
        self.assertEqual(
            response.data["profile"]["region"]["regionCode"],
            self.region.region_code,
        )
        self.assertIsNone(response.data["subscription"])
        self.assertEqual(
            response.data["notificationSettings"],
            {
                "outer": False,
                "exercise": False,
                "laundry": False,
                "umbrella": False,
            },
        )
        self.assertNotIn("activity", response.data)
