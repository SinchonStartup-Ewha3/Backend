import hashlib
import uuid
from datetime import date, timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from fortune.models import (
    FortunePayAppFeedbackEvent,
    FortuneProduct,
    FortuneProfile,
    FortunePurchase,
)
from fortune.services.payapp import create_payment_request


PAYAPP_SETTINGS = {
    "PAYAPP_API_URL": "https://api.payapp.kr/oapi/v2",
    "PAYAPP_USER_ID": "weether",
    "PAYAPP_LINK_KEY": "link-key",
    "PAYAPP_LINK_VALUE": "link-value",
    "PAYAPP_REQUEST_KEY": "request-key",
    "PAYAPP_FORTUNE_FEEDBACK_URL": (
        "https://api.weether.kr/api/fortune/webhooks/payapp/"
    ),
    "PAYAPP_FORTUNE_RETURN_URL": "https://weether.kr/fortune/payment-result",
    "PAYAPP_FORTUNE_ORDER_TAG": "WEE_FORTUNE",
    "PAYAPP_OPEN_PAY_TYPE": "card,kakaopay,naverpay,tosspay",
    "PAYAPP_TIMEOUT_SECONDS": 10,
}


def create_profile(user):
    return FortuneProfile.objects.create(
        user=user,
        calendar_type=FortuneProfile.CalendarType.SOLAR,
        birth_date="2002-05-17",
        converted_solar_date="2002-05-17",
        birth_time=None,
        birth_time_unknown=True,
    )


def create_purchase(user, product, **changes):
    profile = user.fortune_profile
    values = {
        "user": user,
        "product": product,
        "product_title": product.title,
        "duration_days": product.duration_days,
        "amount": product.price,
        "calendar_type": profile.calendar_type,
        "birth_date": profile.birth_date,
        "converted_solar_date": profile.converted_solar_date,
        "birth_time": profile.birth_time,
        "birth_time_unknown": profile.birth_time_unknown,
    }
    values.update(changes)
    return FortunePurchase.objects.create(**values)


@override_settings(**PAYAPP_SETTINGS)
class FortunePayAppCheckoutTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(nickname="운세결제사용자")
        create_profile(self.user)
        self.client.force_authenticate(self.user)
        self.product = FortuneProduct.objects.get(product_code="FORTUNE_7D")

    def test_login_is_required(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            reverse("fortune-payapp-checkout"),
            {"product_id": self.product.pk, "recvphone": "01012345678"},
        )

        self.assertEqual(response.status_code, 401)

    def test_rejects_invalid_phone(self):
        response = self.client.post(
            reverse("fortune-payapp-checkout"),
            {"product_id": self.product.pk, "recvphone": "010-1234-5678"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(FortunePurchase.objects.exists())

    def test_purchase_status_is_visible_only_to_owner(self):
        purchase = create_purchase(self.user, self.product)

        response = self.client.get(
            reverse("fortune-purchase-detail", args=[purchase.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["payment_status"], "PENDING")

        other = get_user_model().objects.create_user(nickname="다른운세사용자")
        self.client.force_authenticate(other)
        self.assertEqual(
            self.client.get(
                reverse("fortune-purchase-detail", args=[purchase.pk])
            ).status_code,
            404,
        )

    @patch("fortune.views.create_fortune_payment_request")
    def test_creates_purchase_and_returns_payapp_url(self, mocked_request):
        mocked_request.return_value = {
            "state": "1",
            "mul_no": "70001",
            "payurl": "https://payapp.kr/pay/70001",
        }

        response = self.client.post(
            reverse("fortune-payapp-checkout"),
            {"product_id": self.product.pk, "recvphone": "01012345678"},
        )

        self.assertEqual(response.status_code, 201)
        purchase = FortunePurchase.objects.get(pk=response.data["purchaseId"])
        self.assertEqual(purchase.amount, self.product.price)
        self.assertEqual(purchase.payment_key, "payapp:70001")
        self.assertIsNotNone(purchase.payapp_order_token)
        self.assertEqual(response.data["paymentUrl"], "https://payapp.kr/pay/70001")
        mocked_request.assert_called_once_with(
            purchase=purchase,
            recvphone="01012345678",
        )

    @patch("fortune.services.payapp.requests.post")
    def test_payapp_request_uses_server_product_price_and_token(self, mocked_post):
        purchase = create_purchase(self.user, self.product)
        mocked_post.return_value = Mock(
            status_code=200,
            text=(
                "state=1&errorMessage=&mul_no=70002&"
                "payurl=https%3A%2F%2Fpayapp.kr%2Fpay%2F70002"
            ),
        )

        result = create_payment_request(
            purchase=purchase,
            recvphone="01098765432",
        )

        purchase.refresh_from_db()
        self.assertEqual(result["mul_no"], "70002")
        payload = mocked_post.call_args.kwargs["data"]
        self.assertEqual(payload["goodname"], self.product.title)
        self.assertEqual(payload["price"], str(self.product.price))
        self.assertEqual(payload["var1"], str(purchase.payapp_order_token))
        self.assertEqual(payload["var2"], "WEE_FORTUNE")
        self.assertEqual(
            payload["feedbackurl"],
            PAYAPP_SETTINGS["PAYAPP_FORTUNE_FEEDBACK_URL"],
        )


@override_settings(**PAYAPP_SETTINGS)
class FortunePayAppFeedbackTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(nickname="운세통보사용자")
        create_profile(self.user)
        self.product = FortuneProduct.objects.get(product_code="FORTUNE_7D")
        self.purchase = create_purchase(
            self.user,
            self.product,
            payapp_order_token=uuid.uuid4(),
            payment_key="payapp:90001",
        )
        self.url = reverse("fortune-payapp-feedback")

    def feedback(self, *, state="4", responsedate="20261029120000", **changes):
        payload = {
            "userid": "weether",
            "linkkey": "link-key",
            "linkval": "link-value",
            "responsedate": responsedate,
            "goodname": self.purchase.product_title,
            "price": str(self.purchase.amount),
            "pay_state": state,
            "var1": str(self.purchase.payapp_order_token),
            "var2": "WEE_FORTUNE",
            "mul_no": "90001",
        }
        payload.update(changes)
        payload["hash"] = hashlib.sha256(
            (
                payload["userid"]
                + payload["responsedate"]
                + PAYAPP_SETTINGS["PAYAPP_REQUEST_KEY"]
            ).encode()
        ).hexdigest()
        return payload

    def test_completed_payment_activates_exact_product_duration(self):
        response = self.client.post(self.url, self.feedback())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"SUCCESS")
        self.purchase.refresh_from_db()
        self.assertEqual(
            self.purchase.payment_status,
            FortunePurchase.PaymentStatus.PAID,
        )
        self.assertEqual(self.purchase.active_from, date(2026, 10, 29))
        self.assertEqual(self.purchase.active_until, date(2026, 11, 4))
        self.assertEqual(FortunePayAppFeedbackEvent.objects.count(), 1)

    def test_duplicate_feedback_does_not_extend_pass(self):
        payload = self.feedback()
        self.client.post(self.url, payload)
        self.purchase.refresh_from_db()
        first_end = self.purchase.active_until

        response = self.client.post(self.url, payload)

        self.assertEqual(response.status_code, 200)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.active_until, first_end)
        self.assertEqual(FortunePayAppFeedbackEvent.objects.count(), 1)

    def test_invalid_amount_is_rejected(self):
        response = self.client.post(self.url, self.feedback(price="1"))

        self.assertEqual(response.status_code, 400)
        self.purchase.refresh_from_db()
        self.assertEqual(
            self.purchase.payment_status,
            FortunePurchase.PaymentStatus.PENDING,
        )

    def test_second_completed_order_is_stacked_after_active_pass(self):
        active = create_purchase(
            self.user,
            self.product,
            payment_status=FortunePurchase.PaymentStatus.PAID,
            payment_key="coupon:ACTIVE",
            active_from=date(2026, 10, 29),
            active_until=date(2026, 11, 4),
        )

        response = self.client.post(self.url, self.feedback())

        self.assertEqual(response.status_code, 200)
        self.purchase.refresh_from_db()
        self.assertEqual(
            self.purchase.active_from,
            active.active_until + timedelta(days=1),
        )

    def test_approval_cancel_revokes_access(self):
        self.client.post(self.url, self.feedback())

        response = self.client.post(
            self.url,
            self.feedback(state="9", responsedate="20261029130000"),
        )

        self.assertEqual(response.status_code, 200)
        self.purchase.refresh_from_db()
        self.assertEqual(
            self.purchase.payment_status,
            FortunePurchase.PaymentStatus.REFUNDED,
        )
