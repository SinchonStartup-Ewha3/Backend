import csv
import os
import tempfile
from unittest.mock import patch
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db.models.query import QuerySet
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from fortune.models import (
    FortuneCoupon,
    FortuneCouponAttempt,
    FortuneProduct,
    FortuneProfile,
    FortunePurchase,
)
from fortune.services.coupons import CODE_ALPHABET, MAX_FAILED_ATTEMPTS

User = get_user_model()


def get_product(code="FORTUNE_7D"):
    # 0002 마이그레이션이 넣어둔 상품을 쓴다
    return FortuneProduct.objects.get(product_code=code)


class CouponRedeemAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(nickname="쿠폰유저")
        FortuneProfile.objects.create(
            user=self.user, calendar_type="SOLAR",
            birth_date="2002-05-17", converted_solar_date="2002-05-17",
            birth_time_unknown=True,
        )
        self.client.force_authenticate(self.user)
        self.url = reverse("fortune-coupon-redeem")
        self.today = timezone.localdate()
        self.coupon = FortuneCoupon.objects.create(code="K7QM", product=get_product())

    def redeem(self, code):
        return self.client.post(self.url, {"code": code}, format="json")

    def test_redeem_creates_paid_purchase(self):
        res = self.redeem("K7QM")

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["payment_status"], "PAID")
        self.assertEqual(res.data["amount"], 0)
        self.assertEqual(res.data["active_from"], str(self.today))
        self.assertEqual(res.data["active_until"], str(self.today + timedelta(days=6)))
        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.redeemed_by, self.user)
        self.assertIsNotNone(self.coupon.purchase)

    def test_code_is_case_and_hyphen_insensitive(self):
        res = self.redeem(" k7-qm ")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_redeemed_coupon_unlocks_today_detail(self):
        self.redeem("K7QM")
        res = self.client.get(reverse("today-fortune-result"))
        self.assertFalse(res.data["detail_locked"])

    def test_code_cannot_be_used_twice(self):
        self.redeem("K7QM")
        other = User.objects.create_user(nickname="다른유저")
        FortuneProfile.objects.create(
            user=other, calendar_type="SOLAR",
            birth_date="2000-01-01", converted_solar_date="2000-01-01",
            birth_time_unknown=True,
        )
        self.client.force_authenticate(other)

        res = self.redeem("K7QM")

        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data["code"], "COUPON_ALREADY_USED")

    def test_invalid_code(self):
        res = self.redeem("ZZZZ")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "COUPON_INVALID")

    def test_inactive_code_is_invalid(self):
        self.coupon.is_active = False
        self.coupon.save()
        res = self.redeem("K7QM")
        self.assertEqual(res.data["code"], "COUPON_INVALID")

    def test_expired_code(self):
        self.coupon.expires_on = self.today - timedelta(days=1)
        self.coupon.save()
        res = self.redeem("K7QM")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "COUPON_EXPIRED")

    def test_profile_required(self):
        FortuneProfile.objects.filter(user=self.user).delete()
        res = self.redeem("K7QM")
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data["code"], "FORTUNE_PROFILE_REQUIRED")

    def test_extends_after_active_purchase(self):
        FortuneCoupon.objects.create(code="ABCD", product=get_product("FORTUNE_1D"))
        self.redeem("K7QM")  # 오늘 ~ 6일 뒤

        res = self.redeem("ABCD")

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["active_from"], str(self.today + timedelta(days=7)))
        self.assertEqual(res.data["active_until"], str(self.today + timedelta(days=7)))

    @override_settings(FORTUNE_COUPON_STACK_POLICY="BLOCK")
    def test_block_policy(self):
        FortuneCoupon.objects.create(code="ABCD", product=get_product("FORTUNE_1D"))
        self.redeem("K7QM")

        res = self.redeem("ABCD")

        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data["code"], "ACTIVE_PURCHASE_EXISTS")
        self.assertFalse(FortuneCoupon.objects.get(code="ABCD").redeemed_at)

    def test_locks_after_too_many_failures(self):
        for _ in range(MAX_FAILED_ATTEMPTS):
            self.redeem("ZZZZ")

        res = self.redeem("K7QM")  # 맞는 코드여도 잠금 중이면 거절

        self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(res.data["code"], "COUPON_TOO_MANY_ATTEMPTS")
        self.assertIsNone(FortuneCoupon.objects.get(code="K7QM").redeemed_at)
        # 잠금은 DB에 저장된다 (worker가 여러 개여도 같은 값을 본다)
        attempt = FortuneCouponAttempt.objects.get(user=self.user)
        self.assertGreater(attempt.locked_until, timezone.now())

    def test_failures_below_limit_are_counted_in_db(self):
        self.redeem("ZZZZ")
        self.redeem("YYYY")
        attempt = FortuneCouponAttempt.objects.get(user=self.user)
        self.assertEqual(attempt.failed_count, 2)
        self.assertIsNone(attempt.locked_until)

    def test_lock_expires(self):
        FortuneCouponAttempt.objects.create(
            user=self.user, locked_until=timezone.now() - timedelta(seconds=1),
        )
        res = self.redeem("K7QM")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_success_resets_failures(self):
        self.redeem("ZZZZ")
        self.redeem("YYYY")

        self.redeem("K7QM")

        attempt = FortuneCouponAttempt.objects.get(user=self.user)
        self.assertEqual(attempt.failed_count, 0)
        self.assertIsNone(attempt.locked_until)

    def test_profile_required_is_not_counted(self):
        FortuneProfile.objects.filter(user=self.user).delete()
        self.redeem("K7QM")
        self.assertEqual(FortuneCouponAttempt.objects.get(user=self.user).failed_count, 0)

    def test_attempts_during_lock_do_not_extend_it(self):
        locked_until = timezone.now() + timedelta(minutes=10)
        FortuneCouponAttempt.objects.create(user=self.user, locked_until=locked_until)

        self.redeem("ZZZZ")

        attempt = FortuneCouponAttempt.objects.get(user=self.user)
        self.assertEqual(attempt.locked_until, locked_until)
        self.assertEqual(attempt.failed_count, 0)

    def test_user_row_is_locked_before_checking_passes(self):
        """같은 사용자의 동시 등록이 순서대로 처리되도록 사용자 행을 먼저 잠근다."""
        original = QuerySet.select_for_update
        locked_models = []

        def spy(queryset, *args, **kwargs):
            locked_models.append(queryset.model)
            return original(queryset, *args, **kwargs)

        with patch.object(QuerySet, "select_for_update", autospec=True, side_effect=spy):
            self.redeem("K7QM")

        self.assertEqual(locked_models[0], User)  # 가장 먼저 사용자 행을 잠근다
        self.assertIn(FortunePurchase, locked_models)

    def test_login_required(self):
        self.client.force_authenticate(user=None)
        res = self.redeem("K7QM")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class CreateCouponsCommandTests(TestCase):
    def test_creates_codes_and_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "codes.csv")
            call_command(
                "create_fortune_coupons",
                product="FORTUNE_7D", count=20, batch="테스트", output=path,
                stdout=open(os.devnull, "w"),
            )
            with open(path, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))

        self.assertEqual(len(rows), 20)
        self.assertEqual(FortuneCoupon.objects.filter(batch_label="테스트").count(), 20)
        for row in rows:
            self.assertEqual(len(row["code"]), 6)
            self.assertTrue(set(row["code"]) <= set(CODE_ALPHABET))