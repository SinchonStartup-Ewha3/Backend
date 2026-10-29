import hashlib
from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User

from .models import PayAppFeedbackEvent, PayAppPayment, PremiumEntitlement
from .services.payapp import create_payment_request


PAYAPP_SETTINGS = {
    "PAYAPP_API_URL": "https://api.payapp.kr/oapi/v2",
    "PAYAPP_USER_ID": "weether",
    "PAYAPP_LINK_KEY": "link-key",
    "PAYAPP_LINK_VALUE": "link-value",
    "PAYAPP_REQUEST_KEY": "request-key",
    "PAYAPP_FEEDBACK_URL": "https://api.weether.kr/api/premium/webhooks/payapp/",
    "PAYAPP_RETURN_URL": "https://weether.kr/premium/payment-result",
    "PAYAPP_OPEN_PAY_TYPE": "card,kakaopay,naverpay,tosspay",
    "PAYAPP_PRODUCT_NAME": "WEE Premium",
    "PAYAPP_ORDER_TAG": "WEE_PREMIUM_21D",
    "PAYAPP_PREMIUM_AMOUNT": 2500,
    "PAYAPP_PREMIUM_CURRENCY": "KRW",
    "PAYAPP_PREMIUM_DURATION_DAYS": 21,
    "PAYAPP_TIMEOUT_SECONDS": 10,
}


@override_settings(**PAYAPP_SETTINGS)
class PayAppCheckoutAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(nickname="페이앱결제사용자")
        self.client.force_authenticate(self.user)

    def test_login_is_required(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            reverse("premium:payapp-checkout"),
            {"recvphone": "01012345678"},
        )
        self.assertEqual(response.status_code, 401)

    def test_rejects_invalid_phone(self):
        response = self.client.post(
            reverse("premium:payapp-checkout"),
            {"recvphone": "010-1234-5678"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(PayAppPayment.objects.exists())

    @patch("premium.views.create_payment_request")
    def test_creates_server_side_payment_request(self, mocked_request):
        mocked_request.return_value = {
            "state": "1",
            "mul_no": "12345678",
            "payurl": "https://payapp.kr/pay/test",
        }
        response = self.client.post(
            reverse("premium:payapp-checkout"),
            {"recvphone": "01012345678"},
        )

        self.assertEqual(response.status_code, 201)
        payment = PayAppPayment.objects.get(pk=response.data["paymentId"])
        self.assertEqual(payment.user, self.user)
        self.assertEqual(payment.amount, 2500)
        self.assertEqual(payment.product_name, "WEE Premium")
        self.assertEqual(payment.buyer_phone_masked, "***-****-5678")
        self.assertEqual(payment.mul_no, "12345678")
        self.assertEqual(response.data["paymentUrl"], payment.pay_url)
        mocked_request.assert_called_once_with(
            payment=payment,
            recvphone="01012345678",
        )

    @patch("premium.services.payapp.requests.post")
    def test_payapp_request_uses_only_server_product_and_order_token(self, mocked_post):
        payment = PayAppPayment.objects.create(
            user=self.user,
            product_name="WEE Premium",
            amount=2500,
            currency_code="KRW",
        )
        mocked_post.return_value = Mock(
            status_code=200,
            text=(
                "state=1&errorMessage=&mul_no=4567&"
                "payurl=https%3A%2F%2Fpayapp.kr%2Fpay%2F4567"
            ),
        )

        result = create_payment_request(
            payment=payment,
            recvphone="01098765432",
        )

        self.assertEqual(result["mul_no"], "4567")
        call = mocked_post.call_args
        payload = call.kwargs["data"]
        self.assertEqual(payload["cmd"], "payrequest")
        self.assertEqual(payload["userid"], "weether")
        self.assertEqual(payload["goodname"], "WEE Premium")
        self.assertEqual(payload["price"], "2500")
        self.assertEqual(payload["recvphone"], "01098765432")
        self.assertEqual(payload["feedbackurl"], PAYAPP_SETTINGS["PAYAPP_FEEDBACK_URL"])
        self.assertEqual(payload["var1"], str(payment.order_token))
        self.assertEqual(payload["var2"], "WEE_PREMIUM_21D")
        self.assertEqual(payload["checkretry"], "y")
        self.assertEqual(payload["smsuse"], "n")


@override_settings(**PAYAPP_SETTINGS)
class PayAppFeedbackTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(nickname="통보검증사용자")
        self.payment = PayAppPayment.objects.create(
            user=self.user,
            mul_no="90001",
            pay_url="https://payapp.kr/pay/90001",
            product_name="WEE Premium",
            amount=2500,
            currency_code="KRW",
            buyer_phone_masked="***-****-5678",
        )
        self.url = reverse("premium:payapp-feedback")

    def feedback(self, *, state="4", responsedate="20261029120000", **changes):
        payload = {
            "userid": "weether",
            "linkkey": "link-key",
            "linkval": "link-value",
            "responsedate": responsedate,
            "goodname": "WEE Premium",
            "price": "2500",
            "pay_state": state,
            "var1": str(self.payment.order_token),
            "var2": "WEE_PREMIUM_21D",
            "mul_no": self.payment.mul_no,
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

    def test_completed_payment_grants_exactly_21_days(self):
        response = self.client.post(self.url, self.feedback())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"SUCCESS")
        self.payment.refresh_from_db()
        entitlement = PremiumEntitlement.objects.get(user=self.user)
        self.assertEqual(self.payment.status, PayAppPayment.Status.COMPLETED)
        self.assertEqual(
            entitlement.expires_at - entitlement.started_at,
            timedelta(days=21),
        )
        self.assertEqual(self.payment.entitlement_expires_at, entitlement.expires_at)
        self.assertEqual(PayAppFeedbackEvent.objects.count(), 1)

    def test_duplicate_feedback_does_not_grant_twice(self):
        payload = self.feedback()
        self.client.post(self.url, payload)
        first_expiry = PremiumEntitlement.objects.get(user=self.user).expires_at

        response = self.client.post(self.url, payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PayAppFeedbackEvent.objects.count(), 1)
        self.assertEqual(
            PremiumEntitlement.objects.get(user=self.user).expires_at,
            first_expiry,
        )

    def test_invalid_hash_is_rejected(self):
        payload = self.feedback()
        payload["hash"] = "not-valid"
        response = self.client.post(self.url, payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b"FAIL")
        self.assertFalse(PremiumEntitlement.objects.filter(user=self.user).exists())
        self.assertFalse(PayAppFeedbackEvent.objects.exists())

    def test_invalid_amount_is_rejected(self):
        response = self.client.post(self.url, self.feedback(price="2501"))

        self.assertEqual(response.status_code, 400)
        self.assertFalse(PremiumEntitlement.objects.filter(user=self.user).exists())

    def test_wrong_order_link_is_rejected(self):
        response = self.client.post(
            self.url,
            self.feedback(var1="c13de379-dd60-4218-b68b-ffcebb5d8949"),
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(PremiumEntitlement.objects.filter(user=self.user).exists())

    def test_request_cancel_does_not_grant(self):
        response = self.client.post(self.url, self.feedback(state="8"))

        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PayAppPayment.Status.REQUEST_CANCELED)
        self.assertFalse(PremiumEntitlement.objects.filter(user=self.user).exists())

    def test_approval_cancel_is_tracked_without_automatic_revoke(self):
        self.client.post(self.url, self.feedback())
        entitlement = PremiumEntitlement.objects.get(user=self.user)
        original_expiry = entitlement.expires_at

        response = self.client.post(
            self.url,
            self.feedback(state="9", responsedate="20261029130000"),
        )

        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        entitlement.refresh_from_db()
        self.assertEqual(
            self.payment.status,
            PayAppPayment.Status.APPROVAL_CANCELED,
        )
        self.assertEqual(entitlement.expires_at, original_expiry)
        self.assertIsNone(self.payment.refund_confirmed_at)

    def test_status_reports_payapp_for_active_entitlement(self):
        self.client.post(self.url, self.feedback())
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse("premium:status"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["isPremium"])
        self.assertEqual(response.data["paymentMethod"], "PAYAPP")
