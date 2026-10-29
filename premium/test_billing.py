from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    BankTransferRequest,
    PayAppPayment,
    PremiumEntitlement,
    PremiumPurchase,
    PremiumRefundRequest,
)
from .services.refunds import reject_refund_request, suspend_refund_access


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
            reason="남은 기간 환불",
            requested_amount=2380,
            currency_code="KRW",
            remaining_seconds=20 * 24 * 60 * 60,
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

    def test_returns_latest_payapp_payment_as_non_refundable(self):
        started_at = self.now - timedelta(days=1)
        expires_at = self.now + timedelta(days=20)
        PremiumEntitlement.objects.create(
            user=self.user,
            started_at=started_at,
            expires_at=expires_at,
        )
        payment = PayAppPayment.objects.create(
            user=self.user,
            mul_no="payapp_billing_1",
            product_name="WEE Premium",
            amount=2500,
            currency_code="KRW",
            status=PayAppPayment.Status.COMPLETED,
            entitlement_started_at=started_at,
            entitlement_expires_at=expires_at,
            completed_at=started_at,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        subscription = response.data["subscription"]
        self.assertEqual(subscription["payAppPaymentId"], payment.pk)
        self.assertEqual(subscription["paymentMethod"], "PAYAPP")
        self.assertEqual(subscription["startedAt"], started_at)
        self.assertEqual(subscription["expiresAt"], expires_at)
        self.assertTrue(subscription["isActive"])
        self.assertGreater(subscription["remainingSeconds"], 0)
        self.assertFalse(subscription["canRequestRefund"])

    def test_suspended_bank_transfer_refund_is_not_active(self):
        started_at = self.now - timedelta(days=1)
        expires_at = self.now + timedelta(days=20)
        PremiumEntitlement.objects.create(
            user=self.user,
            started_at=started_at,
            expires_at=expires_at,
        )
        transfer = BankTransferRequest.objects.create(
            user=self.user,
            depositor_name="결제관리사용자",
            status=BankTransferRequest.Status.APPROVED,
            entitlement_started_at=started_at,
            entitlement_expires_at=expires_at,
            reviewed_at=started_at,
        )
        refund_request = PremiumRefundRequest.objects.create(
            user=self.user,
            bank_transfer_request=transfer,
            reason="남은 기간 환불",
            requested_amount=2380,
            currency_code="KRW",
            remaining_seconds=20 * 24 * 60 * 60,
        )
        suspend_refund_access(refund_request, suspended_at=self.now)

        response = self.client.get(self.url)
        status_response = self.client.get(reverse("premium:status"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        subscription = response.data["subscription"]
        self.assertEqual(subscription["paymentMethod"], "BANK_TRANSFER")
        self.assertFalse(subscription["isActive"])
        self.assertEqual(subscription["remainingSeconds"], 0)
        self.assertFalse(subscription["canRequestRefund"])
        self.assertFalse(status_response.data["isPremium"])
        self.assertIsNone(status_response.data["paymentMethod"])

    def test_rejected_bank_transfer_refund_restores_active_status(self):
        started_at = self.now - timedelta(days=1)
        expires_at = self.now + timedelta(days=20)
        PremiumEntitlement.objects.create(
            user=self.user,
            started_at=started_at,
            expires_at=expires_at,
        )
        transfer = BankTransferRequest.objects.create(
            user=self.user,
            depositor_name="결제관리사용자",
            status=BankTransferRequest.Status.APPROVED,
            entitlement_started_at=started_at,
            entitlement_expires_at=expires_at,
            reviewed_at=started_at,
        )
        refund_request = PremiumRefundRequest.objects.create(
            user=self.user,
            bank_transfer_request=transfer,
            reason="남은 기간 환불",
            requested_amount=2380,
            currency_code="KRW",
            remaining_seconds=20 * 24 * 60 * 60,
        )
        suspend_refund_access(refund_request, suspended_at=self.now)
        reject_refund_request(
            refund_request,
            reason="환불 조건에 맞지 않습니다.",
            rejected_at=timezone.now(),
        )

        status_response = self.client.get(reverse("premium:status"))
        billing_response = self.client.get(self.url)

        self.assertTrue(status_response.data["isPremium"])
        self.assertEqual(status_response.data["paymentMethod"], "BANK_TRANSFER")
        subscription = billing_response.data["subscription"]
        self.assertTrue(subscription["isActive"])
        self.assertEqual(subscription["paymentMethod"], "BANK_TRANSFER")
        self.assertFalse(subscription["canRequestRefund"])
