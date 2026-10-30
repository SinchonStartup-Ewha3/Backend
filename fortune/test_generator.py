from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Region
from fortune.models import FortuneProfile, FortuneResult
from fortune.services.characters import CHARACTERS, CHARACTERS_BY_LEVEL
from fortune.services.generator import build_fortune_result, get_or_create_fortune_result
from fortune.services.lucky_actions import LUCKY_ACTIONS
from fortune.services.saju import Element, LuckLevel, day_stem_element, luck_level

User = get_user_model()


class SajuTests(TestCase):
    def test_day_stem_element(self):
        # 2026-10-13은 경신일 → 경(쇠)
        self.assertEqual(day_stem_element(date(2026, 10, 13)), Element.METAL)
        # 2002-05-17은 을유일 → 을(나무)
        self.assertEqual(day_stem_element(date(2002, 5, 17)), Element.WOOD)

    def test_luck_level_relations(self):
        self.assertEqual(luck_level(Element.WOOD, Element.WATER), LuckLevel.GREAT)    # 수생목
        self.assertEqual(luck_level(Element.WOOD, Element.WOOD), LuckLevel.GOOD)      # 같은 기운
        self.assertEqual(luck_level(Element.WOOD, Element.FIRE), LuckLevel.NORMAL)    # 목생화
        self.assertEqual(luck_level(Element.WOOD, Element.EARTH), LuckLevel.CAUTION)  # 목극토
        self.assertEqual(luck_level(Element.WOOD, Element.METAL), LuckLevel.BAD)      # 금극목


class GeneratorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(nickname="운세유저")
        self.profile = FortuneProfile.objects.create(
            user=self.user, calendar_type="SOLAR",
            birth_date="2002-05-17", converted_solar_date=date(2002, 5, 17),
            birth_time_unknown=True,
        )

    def test_same_user_and_date_gives_same_result(self):
        a = build_fortune_result(user=self.user, profile=self.profile, target_date=date(2026, 10, 13))
        b = build_fortune_result(user=self.user, profile=self.profile, target_date=date(2026, 10, 13))
        self.assertEqual(a, b)

    def test_level_from_elements(self):
        # 나무(을유일생) vs 쇠(경신일) → 금극목 → BAD
        result = build_fortune_result(user=self.user, profile=self.profile, target_date=date(2026, 10, 13))
        self.assertEqual(result["luck_level"], LuckLevel.BAD)
        self.assertIn(result["character"], CHARACTERS_BY_LEVEL[LuckLevel.BAD])

    def test_character_sets_title_and_lucky_items(self):
        result = build_fortune_result(user=self.user, profile=self.profile, target_date=date(2026, 10, 13))
        character = CHARACTERS[result["character"]]

        self.assertEqual(result["title"], character.name)
        self.assertEqual(result["lucky_color"], character.color)
        self.assertEqual(result["lucky_item"], character.item)
        self.assertEqual(result["lucky_place"], character.place)
        self.assertTrue(result["detail_text"].startswith(character.detail))

    def test_character_catalog(self):
        grouped = [code for codes in CHARACTERS_BY_LEVEL.values() for code in codes]
        self.assertEqual(len(CHARACTERS), 24)
        self.assertCountEqual(grouped, CHARACTERS)  # 24종이 빠짐·중복 없이 등급에 한 번씩
        self.assertEqual(set(CHARACTERS_BY_LEVEL), set(LuckLevel))

    def test_rain_adds_lucky_action(self):
        result = build_fortune_result(
            user=self.user, profile=self.profile, target_date=date(2026, 10, 13), weather="RAIN",
        )
        self.assertTrue(any(action in result["detail_text"] for action in LUCKY_ACTIONS["RAIN"]))
        self.assertEqual(result["weather_condition"], "RAIN")

    def test_without_weather_detail_is_character_only(self):
        result = build_fortune_result(user=self.user, profile=self.profile, target_date=date(2026, 10, 13))
        self.assertEqual(result["detail_text"], CHARACTERS[result["character"]].detail)

    def test_without_location_weather_is_none(self):
        result = get_or_create_fortune_result(user=self.user, target_date=date(2026, 10, 13))
        self.assertIsNone(result.weather_condition)

    @patch("home.services.weather.get_current_weather", side_effect=RuntimeError("기상청 오류"))
    def test_weather_error_falls_back(self, _):
        region = Region.objects.create(
            region_code="1114055000", region_name="서울특별시 중구 소공동",
            lat="37.5638", lng="126.9795", grid_nx=60, grid_ny=127,
        )
        self.user.region = region
        self.user.save()

        result = get_or_create_fortune_result(user=self.user, target_date=date(2026, 10, 13))

        self.assertIsNone(result.weather_condition)
        self.assertTrue(result.lucky_item)


class TodayFortuneAPITests(APITestCase):
    def setUp(self):
        self.region = Region.objects.create(
            region_code="1114055000", region_name="서울특별시 중구 소공동",
            lat="37.5638", lng="126.9795", grid_nx=60, grid_ny=127,
        )
        self.user = User.objects.create_user(nickname="오늘운세", region=self.region)
        FortuneProfile.objects.create(
            user=self.user, calendar_type="SOLAR",
            birth_date="2002-05-17", converted_solar_date=date(2002, 5, 17),
            birth_time_unknown=True,
        )
        self.client.force_authenticate(self.user)

    @patch("home.services.weather.get_current_weather", return_value={"condition": "RAIN"})
    def test_today_includes_luck_and_weather(self, mock_weather):
        res = self.client.get(reverse("today-fortune-result"))

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(res.data["luck_level"], LuckLevel.values)
        self.assertTrue(res.data["luck_label"])
        self.assertTrue(res.data["summary"])
        self.assertEqual(res.data["weather_condition"], "RAIN")
        self.assertEqual(res.data["weather_label"], "비오는 하루")
        self.assertIsNone(res.data["detail_text"])  # 무료는 상세 풀이 잠김

    @patch("home.services.weather.get_current_weather", return_value={"condition": "RAIN"})
    def test_weather_is_fetched_once_per_day(self, mock_weather):
        self.client.get(reverse("today-fortune-result"))
        self.client.get(reverse("today-fortune-result"))

        self.assertEqual(mock_weather.call_count, 1)
        self.assertEqual(FortuneResult.objects.filter(user=self.user).count(), 1)

class LegacyResultTests(APITestCase):
    """새 로직 이전에 만들어진 임시 결과(요약 비어 있음)는 조회 시 다시 계산한다."""

    def setUp(self):
        self.user = User.objects.create_user(nickname="예전결과")
        self.profile = FortuneProfile.objects.create(
            user=self.user, calendar_type="SOLAR",
            birth_date="2002-05-17", converted_solar_date=date(2002, 5, 17),
            birth_time_unknown=True,
        )
        self.client.force_authenticate(self.user)

    def make_legacy(self, target_date):
        # 마이그레이션 직후 기존 행의 모습
        return FortuneResult.objects.create(
            user=self.user, target_date=target_date,
            title="임시 운세", lucky_color="하늘색", lucky_item="손수건",
            lucky_place="햇빛이 잘 드는 카페", detail_text="임시 풀이",
        )

    def test_today_legacy_result_is_recalculated(self):
        from django.utils import timezone

        legacy = self.make_legacy(timezone.localdate())

        res = self.client.get(reverse("today-fortune-result"))

        self.assertEqual(res.data["id"], legacy.id)  # 새 행을 만들지 않고 덮어쓴다
        self.assertTrue(res.data["summary"])
        self.assertNotEqual(res.data["title"], "임시 운세")
        self.assertEqual(FortuneResult.objects.filter(user=self.user).count(), 1)

    def test_result_without_character_is_recalculated_keeping_weather(self):
        from django.utils import timezone

        old = FortuneResult.objects.create(
            user=self.user, target_date=timezone.localdate(),
            title="오늘 운수 좋은 테루테루", luck_level="GOOD", summary="예전 요약",
            weather_condition="SNOW", lucky_color="초록", lucky_item="목도리",
            lucky_place="공원", detail_text="예전 풀이",
        )

        res = self.client.get(reverse("today-fortune-result"))

        self.assertEqual(res.data["id"], old.id)
        self.assertIn(res.data["character"], CHARACTERS)
        self.assertEqual(res.data["weather_condition"], "SNOW")

    def test_new_result_is_not_recalculated(self):
        result = get_or_create_fortune_result(user=self.user, target_date=date(2026, 10, 13))
        FortuneResult.objects.filter(pk=result.pk).update(lucky_color="고정값")

        again = get_or_create_fortune_result(user=self.user, target_date=date(2026, 10, 13))

        self.assertEqual(again.lucky_color, "고정값")

    def test_purchase_result_list_recalculates_past_legacy_results(self):
        from datetime import timedelta

        from django.utils import timezone

        from fortune.models import FortuneProduct, FortunePurchase

        today = timezone.localdate()
        product = FortuneProduct.objects.get(product_code="FORTUNE_7D")
        purchase = FortunePurchase.objects.create(
            user=self.user, product=product, product_title=product.title,
            duration_days=7, amount=product.price, calendar_type="SOLAR",
            birth_date=date(2002, 5, 17), converted_solar_date=date(2002, 5, 17),
            birth_time_unknown=True, payment_status=FortunePurchase.PaymentStatus.PAID,
            active_from=today - timedelta(days=1), active_until=today + timedelta(days=5),
        )
        self.make_legacy(today - timedelta(days=1))

        res = self.client.get(reverse("fortune-result-list", args=[purchase.id]))

        self.assertEqual(len(res.data), 1)
        self.assertTrue(res.data[0]["summary"])
        self.assertIsNone(res.data[0]["weather_condition"])  # 지난 날짜는 날씨 없이