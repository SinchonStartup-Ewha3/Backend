from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    PremiumEntitlement,
    PremiumPurchase,
    PremiumRefundRequest,
)
from .services.refunds import complete_manual_refund


User = get_user_model()


class PremiumRefundRequestAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(nickname="환불요청사용자")
        self.client.force_authenticate(self.user)
        self.now = timezone.now()
        self.entitlement = PremiumEntitlement.objects.create(
            user=self.user,
            started_at=self.now - timedelta(days=1),
            expires_at=self.now + timedelta(days=20),
        )
        self.purchase = PremiumPurchase.objects.create(
            user=self.user,
            paddle_transaction_id="txn_refund_request",
            paddle_price_id="pri_wee_premium",
            amount=2500,
            currency_code="KRW",
            status=PremiumPurchase.Status.COMPLETED,
            entitlement_started_at=self.entitlement.started_at,
            entitlement_expires_at=self.entitlement.expires_at,
            completed_at=self.entitlement.started_at,
        )
        self.url = reverse("premium:refund-request")
        self.payload = {
            "bankName": "토스뱅크",
            "accountNumber": "213-7838-4923-8573",
            "phoneNumber": "010-1234-5678",
        }

    def test_login_is_required(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_creates_request_with_normalized_private_data(self):
        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["purchaseId"], self.purchase.pk)
        self.assertEqual(response.data["status"], "REQUESTED")
        self.assertTrue(response.data["accountNumberMasked"].endswith("8573"))
        self.assertEqual(response.data["phoneNumberMasked"], "010****5678")
        self.assertNotIn("accountNumber", response.data)
        self.assertNotIn("phoneNumber", response.data)

        refund_request = PremiumRefundRequest.objects.get(user=self.user)
        self.assertEqual(refund_request.account_number, "213783849238573")
        self.assertEqual(refund_request.phone_number, "01012345678")

    def test_request_does_not_revoke_before_manual_completion(self):
        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.purchase.refresh_from_db()
        self.entitlement.refresh_from_db()
        self.assertEqual(self.purchase.status, PremiumPurchase.Status.COMPLETED)
        self.assertTrue(self.entitlement.is_active())

    def test_duplicate_request_is_rejected(self):
        first = self.client.post(self.url, self.payload, format="json")
        second = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(second.data["code"], "REFUND_REQUEST_ALREADY_EXISTS")
        self.assertEqual(PremiumRefundRequest.objects.count(), 1)

    def test_invalid_account_and_phone_are_rejected(self):
        response = self.client.post(
            self.url,
            {
                "bankName": "토스뱅크",
                "accountNumber": "invalid-account",
                "phoneNumber": "1234",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("accountNumber", response.data)
        self.assertIn("phoneNumber", response.data)

    def test_no_refundable_purchase_returns_conflict(self):
        self.purchase.status = PremiumPurchase.Status.REFUNDED
        self.purchase.save(update_fields=["status"])

        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "NO_REFUNDABLE_PURCHASE")

    def test_get_returns_latest_request_with_masked_private_data(self):
        self.client.post(self.url, self.payload, format="json")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["bankName"], "토스뱅크")
        self.assertNotIn("accountNumber", response.data)
        self.assertNotIn("phoneNumber", response.data)

    def test_manual_completion_revokes_unused_period(self):
        self.client.post(self.url, self.payload, format="json")
        refund_request = PremiumRefundRequest.objects.get(user=self.user)

        completed = complete_manual_refund(
            refund_request,
            completed_at=self.now,
        )

        self.purchase.refresh_from_db()
        self.entitlement.refresh_from_db()
        self.assertEqual(completed.status, PremiumRefundRequest.Status.COMPLETED)
        self.assertEqual(self.purchase.status, PremiumPurchase.Status.REFUNDED)
        self.assertFalse(self.entitlement.is_active(self.now))
