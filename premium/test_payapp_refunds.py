from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import PayAppPayment, PremiumEntitlement, PremiumRefundRequest
from .services.refunds import complete_payapp_refund, reject_refund_request


User = get_user_model()


class PayAppRefundRequestTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(nickname="페이앱환불사용자")
        self.client.force_authenticate(self.user)
        self.now = timezone.now()
        self.entitlement = PremiumEntitlement.objects.create(
            user=self.user,
            started_at=self.now - timedelta(days=1),
            expires_at=self.now + timedelta(days=20),
        )
        self.payment = PayAppPayment.objects.create(
            user=self.user,
            mul_no="payapp_refund_1",
            product_name="WEE Premium",
            amount=2500,
            currency_code="KRW",
            status=PayAppPayment.Status.COMPLETED,
            provider_state="4",
            entitlement_started_at=self.entitlement.started_at,
            entitlement_expires_at=self.entitlement.expires_at,
            completed_at=self.entitlement.started_at,
        )
        self.url = reverse("premium:refund-request")
        self.payload = {"reason": "남은 기간 환불을 요청합니다."}

    def test_user_can_request_payapp_refund(self):
        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["paymentMethod"], "PAYAPP")
        self.assertEqual(response.data["payAppPaymentId"], self.payment.pk)
        self.assertEqual(response.data["status"], "REQUESTED")
        self.assertEqual(response.data["currencyCode"], "KRW")
        self.assertGreater(response.data["requestedAmount"], 0)

        refund_request = PremiumRefundRequest.objects.get(
            payapp_payment=self.payment,
        )
        self.entitlement.refresh_from_db()
        self.assertEqual(refund_request.user, self.user)
        self.assertIsNotNone(refund_request.access_suspended_at)
        self.assertFalse(self.entitlement.is_active())

        billing = self.client.get(reverse("premium:billing"))
        self.assertFalse(billing.data["subscription"]["isActive"])
        self.assertFalse(billing.data["subscription"]["canRequestRefund"])

    def test_duplicate_payapp_refund_request_is_rejected(self):
        first = self.client.post(self.url, self.payload, format="json")
        second = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(second.data["code"], "REFUND_REQUEST_ALREADY_EXISTS")
        self.assertEqual(PremiumRefundRequest.objects.count(), 1)

    def test_admin_rejection_restores_suspended_access(self):
        self.client.post(self.url, self.payload, format="json")
        refund_request = PremiumRefundRequest.objects.get(
            payapp_payment=self.payment,
        )
        rejected_at = timezone.now() + timedelta(hours=1)

        rejected = reject_refund_request(
            refund_request,
            reason="환불 조건에 맞지 않습니다.",
            rejected_at=rejected_at,
        )

        self.entitlement.refresh_from_db()
        self.assertEqual(rejected.status, PremiumRefundRequest.Status.REJECTED)
        self.assertTrue(self.entitlement.is_active(rejected_at))
        self.assertEqual(
            int((self.entitlement.expires_at - rejected_at).total_seconds()),
            refund_request.remaining_seconds,
        )

    def test_admin_completion_records_payapp_refund(self):
        self.client.post(self.url, self.payload, format="json")
        refund_request = PremiumRefundRequest.objects.get(
            payapp_payment=self.payment,
        )
        completed_at = timezone.now() + timedelta(hours=1)

        completed = complete_payapp_refund(
            refund_request,
            completed_at=completed_at,
        )

        self.payment.refresh_from_db()
        self.entitlement.refresh_from_db()
        self.assertEqual(completed.status, PremiumRefundRequest.Status.COMPLETED)
        self.assertEqual(completed.completed_at, completed_at)
        self.assertEqual(
            self.payment.status,
            PayAppPayment.Status.PARTIALLY_CANCELED,
        )
        self.assertEqual(self.payment.refund_confirmed_at, completed_at)
        self.assertFalse(self.entitlement.is_active(completed_at))

    def test_admin_completion_preserves_provider_approval_cancel_status(self):
        self.client.post(self.url, self.payload, format="json")
        refund_request = PremiumRefundRequest.objects.get(
            payapp_payment=self.payment,
        )
        provider_canceled_at = timezone.now()
        self.payment.status = PayAppPayment.Status.APPROVAL_CANCELED
        self.payment.provider_state = "9"
        self.payment.provider_canceled_at = provider_canceled_at
        self.payment.save(
            update_fields=[
                "status",
                "provider_state",
                "provider_canceled_at",
                "modified_at",
            ]
        )
        completed_at = provider_canceled_at + timedelta(hours=1)

        complete_payapp_refund(
            refund_request,
            completed_at=completed_at,
        )

        self.payment.refresh_from_db()
        self.assertEqual(
            self.payment.status,
            PayAppPayment.Status.APPROVAL_CANCELED,
        )
        self.assertEqual(self.payment.provider_state, "9")
        self.assertEqual(
            self.payment.provider_canceled_at,
            provider_canceled_at,
        )
        self.assertEqual(self.payment.refund_confirmed_at, completed_at)

