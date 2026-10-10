from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    FortuneProduct,
    FortuneProfile,
    FortunePurchase,
    FortuneResult,
)
from .services.payments import PaymentConfirmation


class FortuneAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(nickname="fortune-user")
        self.other_user = get_user_model().objects.create_user(
            nickname="other-user"
        )
        self.client.force_authenticate(self.user)
        self.product, _ = FortuneProduct.objects.update_or_create(
            product_code="FORTUNE_7D",
            defaults={
                "title": "오늘의 운세 7일",
                "description": "7일 동안 매일 상세 풀이를 확인해요.",
                "price": 5900,
                "duration_days": 7,
            },
        )

    def create_profile(self, user=None):
        return FortuneProfile.objects.create(
            user=user or self.user,
            calendar_type=FortuneProfile.CalendarType.SOLAR,
            birth_date="2002-05-17",
            converted_solar_date="2002-05-17",
            birth_time=None,
            birth_time_unknown=True,
        )

    def create_purchase(self, *, user=None, payment_status=None, active=False):
        selected_user = user or self.user
        profile = FortuneProfile.objects.filter(user=selected_user).first()
        profile = profile or self.create_profile(user=selected_user)
        today = timezone.localdate()
        return FortunePurchase.objects.create(
            user=selected_user,
            product=self.product,
            product_title=self.product.title,
            duration_days=self.product.duration_days,
            amount=self.product.price,
            calendar_type=profile.calendar_type,
            birth_date=profile.birth_date,
            converted_solar_date=profile.converted_solar_date,
            birth_time=profile.birth_time,
            birth_time_unknown=profile.birth_time_unknown,
            payment_status=(
                payment_status or FortunePurchase.PaymentStatus.PENDING
            ),
            active_from=today if active else None,
            active_until=today + timedelta(days=6) if active else None,
            purchased_at=timezone.now() if active else None,
        )

    def test_profile_can_be_created_then_retrieved(self):
        url = reverse("fortune-profile")
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)

        create_response = self.client.post(
            url,
            {
                "calendar_type": "SOLAR",
                "birth_date": "2002-05-17",
                "birth_time": None,
                "birth_time_unknown": True,
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            create_response.data["converted_solar_date"],
            "2002-05-17",
        )
        self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK)

    def test_profile_cannot_be_registered_twice(self):
        self.create_profile()

        response = self.client.post(
            reverse("fortune-profile"),
            {
                "calendar_type": "SOLAR",
                "birth_date": "2001-04-03",
                "birth_time": None,
                "birth_time_unknown": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "FORTUNE_PROFILE_ALREADY_EXISTS")

    def test_lunar_profile_is_converted_to_solar(self):
        response = self.client.post(
            reverse("fortune-profile"),
            {
                "calendar_type": "LUNAR_NORMAL",
                "birth_date": "1956-01-21",
                "birth_time": "12:30:00",
                "birth_time_unknown": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["converted_solar_date"], "1956-03-03")

    def test_invalid_lunar_leap_month_is_rejected(self):
        response = self.client.post(
            reverse("fortune-profile"),
            {
                "calendar_type": "LUNAR_LEAP",
                "birth_date": "2017-03-01",
                "birth_time": None,
                "birth_time_unknown": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_product_list_includes_sale_price(self):
        response = self.client.get(reverse("fortune-product-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        product = next(
            item
            for item in response.data
            if item["product_code"] == "FORTUNE_7D"
        )
        self.assertEqual(product["price"], 5900)

    def test_free_today_result_hides_detail_text(self):
        self.create_profile()

        response = self.client.get(reverse("today-fortune-result"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["detail_text"])
        self.assertTrue(response.data["detail_locked"])
        self.assertTrue(response.data["title"])
        self.assertTrue(response.data["lucky_color"])

    def test_paid_today_result_unlocks_detail_text(self):
        self.create_purchase(
            payment_status=FortunePurchase.PaymentStatus.PAID,
            active=True,
        )

        response = self.client.get(reverse("today-fortune-result"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["detail_text"])
        self.assertFalse(response.data["detail_locked"])

    def test_expired_payment_confirmation_does_not_unlock_today_detail(self):
        purchase = self.create_purchase(
            payment_status=FortunePurchase.PaymentStatus.PAID,
            active=True,
        )
        yesterday = timezone.localdate() - timedelta(days=1)
        purchase.active_from = yesterday - timedelta(days=6)
        purchase.active_until = yesterday
        purchase.save(update_fields=["active_from", "active_until"])

        response = self.client.post(
            reverse("fortune-payment-confirm", args=[purchase.id]),
            {"payment_key": "already-paid"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_active_purchase_blocks_another_purchase(self):
        self.create_purchase(
            payment_status=FortunePurchase.PaymentStatus.PAID,
            active=True,
        )

        response = self.client.post(
            reverse("fortune-purchase-create"),
            {"product_id": self.product.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_payment_is_not_marked_paid_without_gateway(self):
        purchase = self.create_purchase()

        response = self.client.post(
            reverse("fortune-payment-confirm", args=[purchase.id]),
            {"payment_key": "test-key"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        purchase.refresh_from_db()
        self.assertEqual(
            purchase.payment_status,
            FortunePurchase.PaymentStatus.PENDING,
        )

    @patch("fortune.views.confirm_payment")
    def test_verified_payment_returns_unlocked_result(self, mock_confirm_payment):
        purchase = self.create_purchase()
        mock_confirm_payment.return_value = PaymentConfirmation(
            payment_key="verified-key",
            order_id=str(purchase.id),
            amount=purchase.amount,
            status="DONE",
        )

        response = self.client.post(
            reverse("fortune-payment-confirm", args=[purchase.id]),
            {"payment_key": "verified-key"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["purchase"]["payment_status"], "PAID")
        self.assertFalse(response.data["result"]["detail_locked"])
        self.assertIsNotNone(response.data["result"]["detail_text"])

    def test_future_results_are_hidden_from_result_list(self):
        purchase = self.create_purchase(
            payment_status=FortunePurchase.PaymentStatus.PAID,
            active=True,
        )
        today = timezone.localdate()
        common_result = {
            "user": self.user,
            "title": "오늘의 운세",
            "lucky_color": "하늘색",
            "lucky_item": "손수건",
            "lucky_place": "카페",
            "detail_text": "상세 풀이",
        }
        FortuneResult.objects.create(target_date=today, **common_result)
        FortuneResult.objects.create(
            target_date=today + timedelta(days=1),
            **common_result,
        )

        response = self.client.get(
            reverse("fortune-result-list", args=[purchase.id])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["target_date"], str(today))
        self.assertFalse(response.data[0]["detail_locked"])

    def test_other_users_purchase_is_not_visible(self):
        purchase = self.create_purchase(
            user=self.other_user,
            payment_status=FortunePurchase.PaymentStatus.PAID,
            active=True,
        )

        response = self.client.get(
            reverse("fortune-result-list", args=[purchase.id])
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
