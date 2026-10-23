"""PostgreSQL에서만 도는 쿠폰 동시 등록 통합 테스트.

SQLite는 select_for_update를 지원하지 않아 실제 동시 요청을 재현할 수 없으므로 건너뛴다.
배포 DB와 같은 PostgreSQL로 테스트할 때 실행된다.
"""
import threading
import time
import unittest
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test import TransactionTestCase

from fortune.models import (
    FortuneCoupon,
    FortuneCouponAttempt,
    FortuneProduct,
    FortuneProfile,
    FortunePurchase,
)
from fortune.services import coupons
from fortune.services.coupons import CouponError, redeem_coupon

User = get_user_model()


@unittest.skipUnless(connection.vendor == "postgresql", "PostgreSQL에서만 실행")
class CouponConcurrencyTests(TransactionTestCase):
    # 0002 마이그레이션이 넣은 상품 데이터를 테스트마다 다시 만든다
    serialized_rollback = True

    def setUp(self):
        self.user = User.objects.create_user(nickname="동시등록")
        FortuneProfile.objects.create(
            user=self.user, calendar_type="SOLAR",
            birth_date="2002-05-17", converted_solar_date="2002-05-17",
            birth_time_unknown=True,
        )
        # 상품을 서로 다르게 한다. 같은 상품이면 쿠폰 조회의 select_related("product")가
        # 상품 행까지 잠가서, 사용자 잠금이 없어도 우연히 순서대로 처리된다.
        FortuneCoupon.objects.create(
            code="AAAAAA", product=FortuneProduct.objects.get(product_code="FORTUNE_7D"),
        )
        FortuneCoupon.objects.create(
            code="BBBBBB", product=FortuneProduct.objects.get(product_code="FORTUNE_1D"),
        )
        # 실패 기록 행을 미리 만들어 둔다. 없으면 두 요청이 이 행을 동시에 만들면서
        # 유니크 제약 대기로 우연히 순서가 맞춰져, 사용자 잠금이 없어도 테스트가 통과한다.
        FortuneCouponAttempt.objects.create(user=self.user)

    def test_two_coupons_at_once_do_not_overlap(self):
        barrier = threading.Barrier(2)
        errors = []

        def redeem(code):
            try:
                barrier.wait()
                redeem_coupon(self.user, code)
            except CouponError as error:
                errors.append(error.code)
            finally:
                connections.close_all()

        original_next_start = coupons._next_start_date

        def slow_next_start(*args, **kwargs):
            # 시작일을 계산한 뒤 잠깐 멈춰서, 잠금이 없다면 두 요청이 같은 시작일을 보게 만든다
            result = original_next_start(*args, **kwargs)
            time.sleep(0.3)
            return result

        with patch.object(coupons, "_next_start_date", side_effect=slow_next_start):
            threads = [threading.Thread(target=redeem, args=(c,)) for c in ("AAAAAA", "BBBBBB")]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(errors, [])
        first, second = FortunePurchase.objects.filter(user=self.user).order_by("active_from")
        # 두 번째 이용권은 첫 번째가 끝난 다음 날부터 시작해야 한다
        self.assertGreater(second.active_from, first.active_until)