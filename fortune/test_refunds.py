from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    FortuneCoupon,
    FortuneProduct,
    FortuneProfile,
    FortunePurchase,
    FortuneRefundRequest,
)
from .services.passes import build_my_passes
from .services.refunds import (
    complete_fortune_refund,
    reject_fortune_refund,
)


User = get_user_model()


class FortuneRefundRequestTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(nickname="운세환불사용자")
        self.client.force_authenticate(self.user)
        FortuneProfile.objects.create(
            user=self.user,
            calendar_type=FortuneProfile.CalendarType.SOLAR,
            birth_date="2002-05-17",
            converted_solar_date="2002-05-17",
            birth_time_unknown=True,
        )
        self.today = timezone.localdate()
        self.product = FortuneProduct.objects.get(product_code="FORTUNE_7D")
        self.purchase = FortunePurchase.objects.create(
            user=self.user,
            product=self.product,
            product_title=self.product.title,
            duration_days=self.product.duration_days,
            amount=self.product.price,
            calendar_type=FortuneProfile.CalendarType.SOLAR,
            birth_date="2002-05-17",
            converted_solar_date="2002-05-17",
            birth_time_unknown=True,
            payment_status=FortunePurchase.PaymentStatus.PAID,
            payment_key="payapp:fortune-refund-1",
            active_from=self.today,
            active_until=self.today + timedelta(days=6),
            purchased_at=timezone.now(),
        )
        self.url = reverse("fortune-refund-request")
        self.payload = {
            "purchaseId": self.purchase.pk,
            "reason": "남은 기간에 대한 환불을 요청합니다.",
        }

    def request_refund(self):
        return self.client.post(self.url, self.payload, format="json")

    def test_request_uses_today_and_stops_access_from_tomorrow(self):
        original_active_until = self.purchase.active_until
        self.assertTrue(
            build_my_passes(self.user, self.today)["current"][
                "can_request_refund"
            ]
        )

        response = self.request_refund()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["purchaseId"], self.purchase.pk)
        self.assertEqual(response.data["paymentMethod"], "PAYAPP")
        self.assertEqual(response.data["requestedAmount"], 5057)
        self.assertEqual(response.data["unusedDays"], 6)
        self.assertEqual(response.data["requestedOn"], str(self.today))
        self.assertEqual(
            response.data["stopFrom"],
            str(self.today + timedelta(days=1)),
        )
        self.assertEqual(response.data["status"], "REQUESTED")

        refund_request = FortuneRefundRequest.objects.get(
            purchase=self.purchase,
        )
        self.purchase.refresh_from_db()
        self.assertEqual(refund_request.original_active_until, original_active_until)
        self.assertEqual(self.purchase.active_until, self.today)
        current = build_my_passes(self.user, self.today)["current"]
        self.assertIsNotNone(current)
        self.assertFalse(current["can_request_refund"])
        self.assertEqual(current["refund_status"], "REQUESTED")
        self.assertIsNone(
            build_my_passes(
                self.user,
                self.today + timedelta(days=1),
            )["current"]
        )

    def test_latest_refund_request_can_be_retrieved(self):
        created = self.request_refund()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["refundRequestId"],
            created.data["refundRequestId"],
        )

    def test_duplicate_request_is_rejected(self):
        first = self.request_refund()
        second = self.request_refund()

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(second.data["code"], "FORTUNE_REFUND_ALREADY_EXISTS")
        self.assertEqual(FortuneRefundRequest.objects.count(), 1)

    def test_pending_refund_blocks_new_purchase_and_coupon(self):
        self.request_refund()
        tomorrow = self.today + timedelta(days=1)

        with patch(
            "fortune.serializers.timezone.localdate",
            return_value=tomorrow,
        ):
            purchase_response = self.client.post(
                reverse("fortune-purchase-create"),
                {"product_id": self.product.pk},
                format="json",
            )

        coupon = FortuneCoupon.objects.create(
            code="REFUNDTEST",
            product=self.product,
        )
        coupon_response = self.client.post(
            reverse("fortune-coupon-redeem"),
            {"code": coupon.code},
            format="json",
        )

        self.assertEqual(
            purchase_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn(
            "환불 요청을 처리 중",
            str(purchase_response.data),
        )
        self.assertEqual(
            coupon_response.status_code,
            status.HTTP_409_CONFLICT,
        )
        self.assertEqual(
            coupon_response.data["code"],
            "FORTUNE_REFUND_PENDING",
        )

    def test_coupon_pass_cannot_be_refunded(self):
        self.purchase.payment_key = "coupon:TEST"
        self.purchase.amount = 0
        self.purchase.save(update_fields=["payment_key", "amount"])

        response = self.request_refund()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "FORTUNE_REFUND_PAYAPP_ONLY")
        self.assertFalse(FortuneRefundRequest.objects.exists())

    def test_last_day_has_no_refundable_unused_days(self):
        self.purchase.active_from = self.today - timedelta(days=6)
        self.purchase.active_until = self.today
        self.purchase.save(update_fields=["active_from", "active_until"])

        response = self.request_refund()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data["code"],
            "NO_REFUNDABLE_FORTUNE_PURCHASE",
        )

    def test_admin_completion_marks_purchase_refunded(self):
        self.request_refund()
        refund_request = FortuneRefundRequest.objects.get(
            purchase=self.purchase,
        )
        completed_at = timezone.now() + timedelta(hours=1)

        completed = complete_fortune_refund(
            refund_request,
            completed_at=completed_at,
        )

        self.purchase.refresh_from_db()
        self.assertEqual(completed.status, FortuneRefundRequest.Status.COMPLETED)
        self.assertEqual(completed.completed_at, completed_at)
        self.assertEqual(
            self.purchase.payment_status,
            FortunePurchase.PaymentStatus.REFUNDED,
        )
        self.assertIsNotNone(build_my_passes(self.user, self.today)["current"])
        self.assertIsNone(
            build_my_passes(
                self.user,
                self.today + timedelta(days=1),
            )["current"]
        )

    def test_admin_completion_accepts_provider_cancel_notification_first(self):
        self.request_refund()
        refund_request = FortuneRefundRequest.objects.get(
            purchase=self.purchase,
        )
        self.purchase.payment_status = FortunePurchase.PaymentStatus.REFUNDED
        self.purchase.save(update_fields=["payment_status"])

        completed = complete_fortune_refund(refund_request)

        self.assertEqual(completed.status, FortuneRefundRequest.Status.COMPLETED)

    def test_rejection_restores_paused_access_days(self):
        original_active_until = self.purchase.active_until
        self.request_refund()
        refund_request = FortuneRefundRequest.objects.get(
            purchase=self.purchase,
        )
        rejected_on = self.today + timedelta(days=3)
        rejected_at = timezone.make_aware(
            datetime.combine(rejected_on, time(hour=12)),
            timezone.get_current_timezone(),
        )

        rejected = reject_fortune_refund(
            refund_request,
            reason="환불 조건에 맞지 않습니다.",
            rejected_at=rejected_at,
        )

        self.purchase.refresh_from_db()
        self.assertEqual(rejected.status, FortuneRefundRequest.Status.REJECTED)
        self.assertEqual(
            self.purchase.active_until,
            original_active_until + timedelta(days=2),
        )
        self.assertEqual(rejected.rejection_reason, "환불 조건에 맞지 않습니다.")

    def test_other_users_purchase_cannot_be_refunded(self):
        other = User.objects.create_user(nickname="다른사용자")
        self.client.force_authenticate(other)

        response = self.request_refund()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data["code"],
            "NO_REFUNDABLE_FORTUNE_PURCHASE",
        )

    def test_blank_reason_is_rejected(self):
        self.payload["reason"] = ""

        response = self.request_refund()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(FortuneRefundRequest.objects.exists())
