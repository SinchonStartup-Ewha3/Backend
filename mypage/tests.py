from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
import io
import os
import shutil
import tempfile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from core.models import Region
from fortune.models import (
    FortuneProduct,
    FortuneProfile,
    FortunePurchase,
    FortuneResult,
)
User = get_user_model()


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

    def test_summary_contains_profile_without_notification_settings(self):
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
        self.assertNotIn("notificationSettings", response.data)
        self.assertNotIn("activity", response.data)

TEST_MEDIA_ROOT = tempfile.mkdtemp()


def make_image_file(name="profile.png", fmt="PNG", content_type="image/png"):
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "skyblue").save(buffer, format=fmt)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class ProfileImageAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            nickname="사진테스트", profile_image="http://k.kakaocdn.net/kakao.jpg",
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse("me-profile-image")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def test_me_returns_kakao_image_by_default(self):
        res = self.client.get(reverse("me"))
        self.assertEqual(res.data["profileImage"], "http://k.kakaocdn.net/kakao.jpg")

    def test_upload_profile_image(self):
        res = self.client.patch(self.url, {"profileImage": make_image_file()}, format="multipart")

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["profileImage"].startswith("http://testserver/media/profiles/"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.uploaded_profile_image)

    def test_upload_replaces_old_file(self):
        self.client.patch(self.url, {"profileImage": make_image_file("a.png")}, format="multipart")
        self.user.refresh_from_db()
        old_path = self.user.uploaded_profile_image.path

        self.client.patch(self.url, {"profileImage": make_image_file("b.png")}, format="multipart")

        self.assertFalse(os.path.exists(old_path))

    def test_delete_restores_kakao_image(self):
        self.client.patch(self.url, {"profileImage": make_image_file()}, format="multipart")

        res = self.client.delete(self.url)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["profileImage"], "http://k.kakaocdn.net/kakao.jpg")

    def test_reject_non_image_file(self):
        fake = SimpleUploadedFile("a.png", b"not an image", content_type="image/png")
        res = self.client.patch(self.url, {"profileImage": fake}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reject_unsupported_type(self):
        gif = make_image_file("a.gif", fmt="GIF", content_type="image/gif")
        res = self.client.patch(self.url, {"profileImage": gif}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(KAKAO_ADMIN_KEY="")
    def test_withdraw_deletes_uploaded_file(self):
        self.client.patch(self.url, {"profileImage": make_image_file()}, format="multipart")
        self.user.refresh_from_db()
        path = self.user.uploaded_profile_image.path

        self.client.delete(reverse("me"))

        self.assertFalse(os.path.exists(path))