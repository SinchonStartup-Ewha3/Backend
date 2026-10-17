from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from fortune.models import FortuneProduct, FortunePurchase

User = get_user_model()


class MyFortunePassAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(nickname="이용권유저")
        self.client.force_authenticate(self.user)
        self.url = reverse("fortune-my-passes")
        self.today = timezone.localdate()
        self.seq = 0

    def make_purchase(self, code, start, *, coupon=True, status_=None, redeemed_days_ago=0):
        self.seq += 1
        product = FortuneProduct.objects.get(product_code=code)
        return FortunePurchase.objects.create(
            user=self.user, product=product, product_title=product.title,
            duration_days=product.duration_days,
            amount=0 if coupon else product.price,
            calendar_type="SOLAR", birth_date=date(2002, 5, 17),
            converted_solar_date=date(2002, 5, 17), birth_time_unknown=True,
            payment_status=status_ or FortunePurchase.PaymentStatus.PAID,
            payment_key=f"coupon:TEST{self.seq:02d}" if coupon else f"pay-{self.seq}",
            active_from=start,
            active_until=start + timedelta(days=product.duration_days - 1),
            purchased_at=timezone.now() - timedelta(days=redeemed_days_ago),
        )

    def test_empty(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, {
            "coins": {"remaining": 0, "total": 0},
            "current": None, "upcoming": [], "latest": None,
        })

    def test_coins_like_wireframe(self):
        # 21일권을 3일 전에 시작 → 오늘 포함 18일 남음 (18/21)
        self.make_purchase("FORTUNE_21D", self.today - timedelta(days=3), redeemed_days_ago=3)

        res = self.client.get(self.url)

        self.assertEqual(res.data["coins"], {"remaining": 18, "total": 21})
        self.assertEqual(res.data["current"]["remaining_days"], 18)
        self.assertEqual(res.data["latest"]["product_title"], "오늘의 운세 21일")

    def test_current_and_upcoming(self):
        current = self.make_purchase("FORTUNE_7D", self.today, redeemed_days_ago=1)
        upcoming = self.make_purchase("FORTUNE_1D", self.today + timedelta(days=7))

        res = self.client.get(self.url)

        self.assertEqual(res.data["current"]["purchase_id"], current.pk)
        self.assertEqual([p["purchase_id"] for p in res.data["upcoming"]], [upcoming.pk])
        self.assertEqual(res.data["coins"], {"remaining": 8, "total": 8})
        self.assertEqual(res.data["latest"]["purchase_id"], upcoming.pk)  # 가장 최근에 받은 것

    def test_only_coupon_passes_are_shown(self):
        # 운세는 앱 결제를 쓰지 않으므로, 쿠폰이 아닌 구매 기록은 보여주지 않는다
        self.make_purchase("FORTUNE_7D", self.today, coupon=False)

        res = self.client.get(self.url)

        self.assertEqual(res.data["coins"], {"remaining": 0, "total": 0})
        self.assertIsNone(res.data["current"])
        self.assertIsNone(res.data["latest"])

    def test_expired_and_unpaid_are_excluded_from_coins(self):
        expired = self.make_purchase("FORTUNE_7D", self.today - timedelta(days=30), redeemed_days_ago=30)
        self.make_purchase("FORTUNE_1D", self.today, status_=FortunePurchase.PaymentStatus.PENDING)

        res = self.client.get(self.url)

        self.assertEqual(res.data["coins"], {"remaining": 0, "total": 0})
        self.assertIsNone(res.data["current"])
        self.assertEqual(res.data["latest"]["purchase_id"], expired.pk)  # 최근 등록일은 남겨서 보여준다

    def test_login_required(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)