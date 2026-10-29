from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    BankTransferRequest,
    PremiumEntitlement,
    PremiumRefundRequest,
)
from .services.bank_transfers import (
    BankTransferStateError,
    approve_bank_transfer,
)
from .services.refunds import complete_bank_transfer_refund


User = get_user_model()


class BankTransferFlowTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(nickname="계좌이체사용자")
        self.reviewer = User.objects.create_user(nickname="입금확인관리자")
        self.client.force_authenticate(self.user)
        self.request_url = reverse("premium:bank-transfer-request")

    def create_request(self):
        return self.client.post(
            self.request_url,
            {"depositorName": " 이서인 ", "amount": 1},
            format="json",
        )

    def test_server_creates_pending_request_with_configured_amount(self):
        response = self.create_request()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["depositorName"], "이서인")
        self.assertEqual(response.data["amount"], 2500)
        self.assertEqual(response.data["currencyCode"], "KRW")
        self.assertEqual(response.data["status"], "PENDING")

    def test_duplicate_pending_request_is_idempotent(self):
        first = self.create_request()
        second = self.create_request()

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["requestId"], second.data["requestId"])

    def test_pending_user_can_complete_survey_but_not_use_premium_settings(self):
        self.create_request()

        profile_response = self.client.get(reverse("premium:profile"))
        settings_response = self.client.get(
            reverse("premium:notification-settings")
        )

        self.assertEqual(profile_response.status_code, status.HTTP_200_OK)
        self.assertEqual(settings_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_approval_grants_21_days_once(self):
        self.create_request()
        transfer = BankTransferRequest.objects.get(user=self.user)

        approved = approve_bank_transfer(transfer, self.reviewer)
        entitlement = PremiumEntitlement.objects.get(user=self.user)

        self.assertEqual(approved.status, BankTransferRequest.Status.APPROVED)
        self.assertEqual(
            (entitlement.expires_at - entitlement.started_at).days,
            21,
        )
        with self.assertRaises(BankTransferStateError):
            approve_bank_transfer(transfer, self.reviewer)

    def test_status_reports_pending_and_bank_transfer_payment(self):
        self.create_request()

        pending_response = self.client.get(reverse("premium:status"))
        transfer = BankTransferRequest.objects.get(user=self.user)
        approve_bank_transfer(transfer, self.reviewer)
        approved_response = self.client.get(reverse("premium:status"))

        self.assertTrue(pending_response.data["canCompleteSurvey"])
        self.assertEqual(pending_response.data["bankTransferStatus"], "PENDING")
        self.assertFalse(pending_response.data["isPremium"])
        self.assertTrue(approved_response.data["isPremium"])
        self.assertEqual(approved_response.data["paymentMethod"], "BANK_TRANSFER")

    def test_reason_only_refund_request_and_manual_completion(self):
        self.create_request()
        transfer = BankTransferRequest.objects.get(user=self.user)
        approve_bank_transfer(transfer, self.reviewer)

        response = self.client.post(
            reverse("premium:refund-request"),
            {"reason": "알림을 더 이상 이용하지 않아요."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["paymentMethod"], "BANK_TRANSFER")
        self.assertEqual(response.data["bankTransferRequestId"], transfer.pk)
        refund_request = PremiumRefundRequest.objects.get(user=self.user)
        entitlement = PremiumEntitlement.objects.get(user=self.user)
        self.assertFalse(entitlement.is_active())

        complete_bank_transfer_refund(
            refund_request,
            completed_at=timezone.now(),
        )

        transfer.refresh_from_db()
        entitlement.refresh_from_db()
        self.assertEqual(transfer.status, BankTransferRequest.Status.REFUNDED)
        self.assertFalse(entitlement.is_active())
