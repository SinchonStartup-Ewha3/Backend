from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import PremiumEntitlement, PremiumPurchase, PremiumRefundRequest


User = get_user_model()


class PremiumBillingAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(nickname="결제관리사용자")
        self.client.force_authenticate(self.user)
        self.url = reverse("premium:billing")
        self.now = timezone.now()

    def create_completed_purchase(self, *, completed_at=None):
        completed_at = completed_at or self.now
        return PremiumPurchase.objects.create(
            user=self.user,
            paddle_transaction_id=f"txn_{completed_at.timestamp()}",
            paddle_price_id="pri_wee_premium",
            amount=2500,
            currency_code="KRW",
            status=PremiumPurchase.Status.COMPLETED,
            entitlement_started_at=completed_at,
            entitlement_expires_at=completed_at + timedelta(days=21),
            completed_at=completed_at,
        )

    def test_login_is_required(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_returns_empty_billing_data_without_purchase(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {"subscription": None},
        )

    def test_returns_active_entitlement_and_latest_purchase(self):
        entitlement = PremiumEntitlement.objects.create(
            user=self.user,
            started_at=self.now - timedelta(days=1),
            expires_at=self.now + timedelta(days=20),
        )
        purchase = self.create_completed_purchase(
            completed_at=entitlement.started_at,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        subscription = response.data["subscription"]
        self.assertTrue(subscription["isActive"])
        self.assertGreater(subscription["remainingSeconds"], 0)
        self.assertEqual(subscription["purchaseId"], purchase.pk)
        self.assertEqual(
            subscription["productName"],
            "맞춤형 행동 알림",
        )
        self.assertTrue(subscription["canRequestRefund"])

    def test_existing_refund_request_disables_refund(self):
        entitlement = PremiumEntitlement.objects.create(
            user=self.user,
            started_at=self.now - timedelta(days=1),
            expires_at=self.now + timedelta(days=20),
        )
        purchase = self.create_completed_purchase(
            completed_at=entitlement.started_at,
        )
        PremiumRefundRequest.objects.create(
            user=self.user,
            purchase=purchase,
            bank_name="토스뱅크",
            account_number="123456789012",
            phone_number="01012345678",
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["subscription"]["canRequestRefund"])

    def test_expired_entitlement_has_zero_remaining_time(self):
        entitlement = PremiumEntitlement.objects.create(
            user=self.user,
            started_at=self.now - timedelta(days=22),
            expires_at=self.now - timedelta(days=1),
        )
        self.create_completed_purchase(completed_at=entitlement.started_at)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        subscription = response.data["subscription"]
        self.assertFalse(subscription["isActive"])
        self.assertEqual(subscription["remainingSeconds"], 0)
        self.assertFalse(subscription["canRequestRefund"])

    def test_latest_completed_purchase_is_returned(self):
        PremiumEntitlement.objects.create(
            user=self.user,
            started_at=self.now - timedelta(days=2),
            expires_at=self.now + timedelta(days=40),
        )
        self.create_completed_purchase(completed_at=self.now - timedelta(days=2))
        latest_purchase = self.create_completed_purchase(
            completed_at=self.now - timedelta(days=1),
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["subscription"]["purchaseId"],
            latest_purchase.pk,
        )
