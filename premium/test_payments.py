import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    PaddleWebhookEvent,
    PremiumEntitlement,
    PremiumPurchase,
    PremiumRefundRequest,
)
from .services.paddle import (
    PaddleWebhookSignatureError,
    create_transaction,
    verify_webhook_signature,
)


User = get_user_model()
PADDLE_SETTINGS = {
    "PADDLE_API_KEY": "pdl_sdbx_test",
    "PADDLE_ENVIRONMENT": "sandbox",
    "PADDLE_WEBHOOK_SECRET": "pdl_ntfset_test_secret",
    "PADDLE_PRICE_ID": "pri_wee_premium",
    "PADDLE_PREMIUM_AMOUNT": 2500,
    "PADDLE_PREMIUM_CURRENCY": "KRW",
    "PADDLE_PREMIUM_DURATION_DAYS": 21,
}


@override_settings(**PADDLE_SETTINGS)
class PremiumCheckoutAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(nickname="결제사용자")
        self.client.force_authenticate(self.user)

    def test_login_is_required(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(reverse("premium:checkout"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("premium.views.create_transaction")
    def test_creates_server_side_transaction_for_configured_price(self, mocked_create):
        mocked_create.return_value = {
            "id": "txn_checkout",
            "checkout": {"url": "https://sandbox-checkout.paddle.com/test"},
        }
        response = self.client.post(reverse("premium:checkout"))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["transactionId"], "txn_checkout")
        purchase = PremiumPurchase.objects.get(pk=response.data["purchaseId"])
        self.assertEqual(purchase.user, self.user)
        self.assertEqual(purchase.paddle_price_id, "pri_wee_premium")
        self.assertEqual(purchase.amount, 2500)
        mocked_create.assert_called_once_with(purchase=purchase)

    @patch("premium.services.paddle.requests.post")
    def test_paddle_request_uses_server_price_and_user_link(self, mocked_post):
        purchase = PremiumPurchase.objects.create(
            user=self.user,
            paddle_price_id="pri_wee_premium",
            amount=2500,
            currency_code="KRW",
        )
        mocked_post.return_value.status_code = 201
        mocked_post.return_value.json.return_value = {
            "data": {
                "id": "txn_api",
                "items": [
                    {
                        "quantity": 1,
                        "price": {
                            "id": "pri_wee_premium",
                            "unit_price": {
                                "amount": "2500",
                                "currency_code": "KRW",
                            },
                        },
                    }
                ],
            }
        }

        create_transaction(purchase=purchase)

        request_kwargs = mocked_post.call_args.kwargs
        self.assertEqual(
            mocked_post.call_args.args[0],
            "https://sandbox-api.paddle.com/transactions",
        )
        self.assertEqual(
            request_kwargs["json"]["items"],
            [{"price_id": "pri_wee_premium", "quantity": 1}],
        )
        self.assertEqual(
            request_kwargs["json"]["custom_data"],
            {
                "wee_purchase_id": str(purchase.pk),
                "wee_user_id": str(self.user.pk),
            },
        )


@override_settings(**PADDLE_SETTINGS)
class PaddleWebhookTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(nickname="웹훅사용자")
        self.purchase = PremiumPurchase.objects.create(
            user=self.user,
            paddle_transaction_id="txn_wee_1",
            paddle_price_id="pri_wee_premium",
            amount=2500,
            currency_code="KRW",
        )
        self.url = reverse("premium:paddle-webhook")

    def payload(self, *, event_id="evt_completed_1", event_type="transaction.completed"):
        return {
            "event_id": event_id,
            "event_type": event_type,
            "notification_id": f"ntf_{event_id}",
            "occurred_at": timezone.now().isoformat(),
            "data": {
                "id": "txn_wee_1",
                "status": "completed",
                "subscription_id": None,
                "customer_id": "ctm_test",
                "currency_code": "KRW",
                "custom_data": {
                    "wee_purchase_id": str(self.purchase.pk),
                    "wee_user_id": str(self.user.pk),
                },
                "items": [
                    {
                        "quantity": 1,
                        "price": {
                            "id": "pri_wee_premium",
                            "product_id": "pro_wee_premium",
                        },
                    }
                ],
                "details": {"totals": {"total": "2500"}},
            },
        }

    def post_payload(self, payload, *, secret="pdl_ntfset_test_secret"):
        body = json.dumps(payload, separators=(",", ":")).encode()
        timestamp = int(time.time())
        signature = hmac.new(
            secret.encode(),
            str(timestamp).encode() + b":" + body,
            hashlib.sha256,
        ).hexdigest()
        return self.client.generic(
            "POST",
            self.url,
            body,
            content_type="application/json",
            HTTP_PADDLE_SIGNATURE=f"ts={timestamp};h1={signature}",
        )

    def test_completed_transaction_grants_exactly_21_days(self):
        response = self.post_payload(self.payload())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.purchase.refresh_from_db()
        entitlement = PremiumEntitlement.objects.get(user=self.user)
        self.assertEqual(self.purchase.status, PremiumPurchase.Status.COMPLETED)
        self.assertEqual(
            entitlement.expires_at - entitlement.started_at,
            timedelta(days=21),
        )

    def test_duplicate_event_does_not_grant_twice(self):
        payload = self.payload()
        first = self.post_payload(payload)
        expires_at = PremiumEntitlement.objects.get(user=self.user).expires_at
        second = self.post_payload(payload)

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertTrue(second.data["duplicate"])
        self.assertEqual(PaddleWebhookEvent.objects.count(), 1)
        self.assertEqual(
            PremiumEntitlement.objects.get(user=self.user).expires_at,
            expires_at,
        )

    def test_unknown_simulator_transaction_is_ignored_without_grant(self):
        payload = self.payload(event_id="ntfsimevt_unknown_transaction")
        payload["notification_id"] = "ntfsimntf_unknown_transaction"
        payload["data"]["id"] = "txn_simulator_missing"

        response = self.post_payload(payload)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["duplicate"])
        self.assertEqual(PaddleWebhookEvent.objects.count(), 1)
        self.assertFalse(PremiumEntitlement.objects.filter(user=self.user).exists())
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, PremiumPurchase.Status.PENDING)

    def test_purchase_lock_query_does_not_join_nullable_user(self):
        from .services.webhooks import _find_purchase

        with transaction.atomic(), CaptureQueriesContext(connection) as queries:
            purchase = _find_purchase(self.purchase.paddle_transaction_id)

        self.assertEqual(purchase, self.purchase)
        select_sql = next(
            query["sql"] for query in queries.captured_queries
            if "premium_premiumpurchase" in query["sql"]
        )
        self.assertNotIn(" JOIN ", select_sql.upper())

    def test_second_purchase_stacks_after_remaining_period(self):
        self.post_payload(self.payload())
        first_entitlement = PremiumEntitlement.objects.get(user=self.user)
        first_end = first_entitlement.expires_at
        second_purchase = PremiumPurchase.objects.create(
            user=self.user,
            paddle_transaction_id="txn_wee_2",
            paddle_price_id="pri_wee_premium",
            amount=2500,
            currency_code="KRW",
        )
        payload = self.payload(event_id="evt_completed_2")
        payload["data"]["id"] = "txn_wee_2"
        payload["data"]["custom_data"]["wee_purchase_id"] = str(second_purchase.pk)

        response = self.post_payload(payload)
        first_entitlement.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_entitlement.expires_at, first_end + timedelta(days=21))

    def test_invalid_amount_is_rejected_without_grant(self):
        payload = self.payload()
        payload["data"]["details"]["totals"]["total"] = "2400"
        response = self.post_payload(payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(PremiumEntitlement.objects.filter(user=self.user).exists())
        self.assertEqual(PaddleWebhookEvent.objects.count(), 0)

    def test_wrong_product_or_user_link_is_rejected(self):
        wrong_product = self.payload(event_id="evt_wrong_product")
        wrong_product["data"]["items"][0]["price"]["id"] = "pri_other"
        product_response = self.post_payload(wrong_product)

        wrong_user = self.payload(event_id="evt_wrong_user")
        wrong_user["data"]["custom_data"]["wee_user_id"] = "999999"
        user_response = self.post_payload(wrong_user)

        self.assertEqual(product_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(user_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(PremiumEntitlement.objects.filter(user=self.user).exists())

    def test_invalid_signature_is_rejected(self):
        response = self.post_payload(self.payload(), secret="wrong-secret")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(PremiumEntitlement.objects.filter(user=self.user).exists())

    @patch("premium.views.logger.exception")
    @patch("premium.views.process_webhook", side_effect=RuntimeError("database failed"))
    def test_unexpected_processing_error_is_logged_and_remains_500(
        self,
        _mocked_process_webhook,
        mocked_logger,
    ):
        self.client.raise_request_exception = False

        response = self.post_payload(self.payload(event_id="evt_unexpected_error"))

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        mocked_logger.assert_called_once()

    def test_past_due_and_canceled_transactions_do_not_grant(self):
        failed_payload = self.payload(
            event_id="evt_failed",
            event_type="transaction.past_due",
        )
        failed_payload["data"]["status"] = "past_due"
        response = self.post_payload(failed_payload)
        self.purchase.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.purchase.status, PremiumPurchase.Status.FAILED)
        self.assertFalse(PremiumEntitlement.objects.filter(user=self.user).exists())

        self.purchase.status = PremiumPurchase.Status.PENDING
        self.purchase.save(update_fields=["status"])
        canceled = self.payload(
            event_id="evt_canceled",
            event_type="transaction.canceled",
        )
        canceled["data"]["status"] = "canceled"
        self.post_payload(canceled)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, PremiumPurchase.Status.CANCELED)

    def test_approved_full_refund_revokes_unused_period(self):
        self.post_payload(self.payload())
        adjustment = {
            "event_id": "evt_refund",
            "event_type": "adjustment.created",
            "notification_id": "ntf_refund",
            "occurred_at": timezone.now().isoformat(),
            "data": {
                "id": "adj_refund",
                "transaction_id": "txn_wee_1",
                "action": "refund",
                "status": "approved",
                "type": "full",
            },
        }
        response = self.post_payload(adjustment)

        self.purchase.refresh_from_db()
        entitlement = PremiumEntitlement.objects.get(user=self.user)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.purchase.status, PremiumPurchase.Status.REFUNDED)
        self.assertFalse(entitlement.is_active())

    def test_approved_prorated_refund_completes_request_and_revokes_unused_period(self):
        self.post_payload(self.payload())
        refund_request = PremiumRefundRequest.objects.create(
            user=self.user,
            purchase=self.purchase,
            reason="남은 기간 환불",
            requested_amount=2000,
            currency_code="KRW",
            remaining_seconds=18 * 24 * 60 * 60,
        )
        adjustment = {
            "event_id": "evt_partial_refund",
            "event_type": "adjustment.created",
            "notification_id": "ntf_partial_refund",
            "occurred_at": timezone.now().isoformat(),
            "data": {
                "id": "adj_partial_refund",
                "transaction_id": "txn_wee_1",
                "action": "refund",
                "status": "approved",
                "type": "partial",
                "totals": {"total": "2000"},
            },
        }

        response = self.post_payload(adjustment)

        self.purchase.refresh_from_db()
        refund_request.refresh_from_db()
        entitlement = PremiumEntitlement.objects.get(user=self.user)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.purchase.status,
            PremiumPurchase.Status.PARTIALLY_REFUNDED,
        )
        self.assertEqual(
            refund_request.status,
            PremiumRefundRequest.Status.COMPLETED,
        )
        self.assertEqual(
            refund_request.paddle_adjustment_id,
            "adj_partial_refund",
        )
        self.assertIsNotNone(refund_request.completed_at)
        self.assertFalse(entitlement.is_active())

    def test_pending_then_rejected_refund_updates_request_without_revoking(self):
        self.post_payload(self.payload())
        refund_request = PremiumRefundRequest.objects.create(
            user=self.user,
            purchase=self.purchase,
            reason="남은 기간 환불",
            requested_amount=2000,
            currency_code="KRW",
            remaining_seconds=18 * 24 * 60 * 60,
        )
        adjustment = {
            "event_id": "evt_pending_refund",
            "event_type": "adjustment.created",
            "notification_id": "ntf_pending_refund",
            "occurred_at": timezone.now().isoformat(),
            "data": {
                "id": "adj_pending_refund",
                "transaction_id": "txn_wee_1",
                "action": "refund",
                "status": "pending_approval",
                "type": "partial",
                "totals": {"total": "2000"},
            },
        }

        self.post_payload(adjustment)
        refund_request.refresh_from_db()
        self.assertEqual(
            refund_request.status,
            PremiumRefundRequest.Status.PROCESSING,
        )

        adjustment["event_id"] = "evt_rejected_refund"
        adjustment["notification_id"] = "ntf_rejected_refund"
        adjustment["event_type"] = "adjustment.updated"
        adjustment["data"]["status"] = "rejected"
        self.post_payload(adjustment)

        self.purchase.refresh_from_db()
        refund_request.refresh_from_db()
        entitlement = PremiumEntitlement.objects.get(user=self.user)
        self.assertEqual(self.purchase.status, PremiumPurchase.Status.COMPLETED)
        self.assertEqual(
            refund_request.status,
            PremiumRefundRequest.Status.REJECTED,
        )
        self.assertTrue(entitlement.is_active())

    def test_refund_delivered_before_completed_event_never_grants(self):
        adjustment = {
            "event_id": "evt_refund_first",
            "event_type": "adjustment.created",
            "notification_id": "ntf_refund_first",
            "occurred_at": timezone.now().isoformat(),
            "data": {
                "id": "adj_refund_first",
                "transaction_id": "txn_wee_1",
                "action": "refund",
                "status": "approved",
                "type": "full",
            },
        }
        self.post_payload(adjustment)
        response = self.post_payload(self.payload(event_id="evt_completed_late"))

        self.purchase.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.purchase.status, PremiumPurchase.Status.REFUNDED)
        self.assertFalse(PremiumEntitlement.objects.filter(user=self.user).exists())


@override_settings(**PADDLE_SETTINGS)
class PremiumStatusTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(nickname="상태사용자")
        self.client.force_authenticate(self.user)

    def test_expired_entitlement_is_not_premium(self):
        PremiumEntitlement.objects.create(
            user=self.user,
            started_at=timezone.now() - timedelta(days=22),
            expires_at=timezone.now() - timedelta(days=1),
        )
        response = self.client.get(reverse("premium:status"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["isPremium"])
        self.assertEqual(response.data["remainingSeconds"], 0)

    def test_expired_entitlement_cannot_access_premium_feature(self):
        PremiumEntitlement.objects.create(
            user=self.user,
            started_at=timezone.now() - timedelta(days=22),
            expires_at=timezone.now() - timedelta(days=1),
        )
        response = self.client.get(reverse("premium:profile"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(PADDLE_WEBHOOK_SECRET="signature-secret", PADDLE_ENVIRONMENT="sandbox")
class WebhookSignatureUnitTests(APITestCase):
    def test_old_signature_is_rejected(self):
        body = b'{}'
        old_timestamp = 100
        signature = hmac.new(
            b"signature-secret",
            b"100:{}",
            hashlib.sha256,
        ).hexdigest()
        with self.assertRaises(PaddleWebhookSignatureError):
            verify_webhook_signature(
                body,
                f"ts={old_timestamp};h1={signature}",
                now=1000,
                tolerance=5,
            )
