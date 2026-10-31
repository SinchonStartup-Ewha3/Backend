from datetime import date
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from fortune.models import FortuneProfile
from fortune.services.characters import CHARACTERS
from fortune.services.fortune_writer import write_fortune_detail
from fortune.services.generator import build_fortune_result, get_or_create_fortune_result
from fortune.services.lucky_actions import LUCKY_ACTIONS, pick_lucky_action, weather_category

User = get_user_model()

AI_SETTINGS = {
    "OPENAI_FORTUNE_ENABLED": True,
    "OPENAI_API_KEY": "test-key",
    "OPENAI_API_URL": "https://api.openai.com/v1/responses",
    "OPENAI_FORTUNE_MODEL": "test-model",
    "OPENAI_TIMEOUT_SECONDS": 8,
}
AI_TEXT = (
    "마음속에만 두었던 일을 작게라도 시작하기 좋은 날이에요. 오늘의 흐름이 스스로 움직이려는 힘을 북돋아 주니, "
    "첫걸음을 내디디면 생각보다 자연스럽게 다음 순서가 보일 수 있어요. 사람들과 이야기할 때는 정답을 서둘러 내기보다 "
    "상대의 말을 한 번 더 들어주면 관계의 온도가 한결 부드러워질 거예요. 여러 일을 한꺼번에 벌이기보다는 가장 중요한 "
    "한 가지를 골라 끝까지 마무리해 보세요. 작은 노트에 떠오른 생각을 적어두면 놓치기 쉬운 힌트를 붙잡는 데 도움이 돼요. "
    "하늘이 맑다면 잠깐 햇빛을 쐬며 머릿속을 환기해보는 것도 오늘의 좋은 마무리가 될 거예요."
)


def ai_response(text):
    return Mock(
        status_code=200,
        raise_for_status=Mock(),
        json=Mock(return_value={
            "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
        }),
    )


class WeatherCategoryTests(SimpleTestCase):
    def test_categories(self):
        cases = [
            (None, None),
            ({"condition": "CLEAR"}, "CLEAR"),
            ({"condition": "PARTLY_CLOUDY"}, "CLOUDY"),
            ({"condition": "SHOWER"}, "RAIN"),
            ({"condition": "SNOW", "feelsLike": 40}, "SNOW"),
            ({"condition": "CLEAR", "feelsLike": 34}, "HOT"),
            ({"condition": "CLEAR", "feelsLike": -8}, "COLD"),
            ({"condition": "CLOUDY", "windSpeed": 10}, "WINDY"),
            ({"condition": "CLEAR", "minTemperature": 5, "maxTemperature": 16}, "TEMP_GAP"),
            ({"condition": "FOG"}, "FOG"),
            ({"condition": "CLEAR", "airQuality": {"grade": "BAD"}}, "FINE_DUST"),
            ({"airQuality": {"pm10": 81}}, "FINE_DUST"),
        ]
        for weather, expected in cases:
            with self.subTest(weather=weather):
                self.assertEqual(weather_category(weather), expected)

    def test_all_fifty_lucky_actions_are_registered(self):
        self.assertEqual(sum(map(len, LUCKY_ACTIONS.values())), 50)

    def test_pick_is_stable(self):
        a = pick_lucky_action("RAIN", "1:2026-10-30")
        self.assertEqual(a, pick_lucky_action("RAIN", "1:2026-10-30"))
        self.assertIn(a, LUCKY_ACTIONS["RAIN"])
        self.assertIsNone(pick_lucky_action(None, "1:2026-10-30"))


class FortuneWriterTests(SimpleTestCase):
    def write(self):
        return write_fortune_detail(
            character=CHARACTERS["KING"], luck_label="매우 좋은", summary="요약",
            target_date=date(2026, 10, 30), birth_element_label="나무",
            today_element_label="물", energy_relation="오늘의 기운이 사용자를 북돋는 상생 흐름",
            weather_label="맑음", lucky_action=LUCKY_ACTIONS["CLEAR"][0],
        )

    @override_settings(OPENAI_FORTUNE_ENABLED=False)
    @patch("fortune.services.fortune_writer.requests.post")
    def test_disabled_does_not_call_api(self, mocked_post):
        self.assertIsNone(self.write())
        mocked_post.assert_not_called()

    @override_settings(**AI_SETTINGS)
    @patch("fortune.services.fortune_writer.requests.post")
    def test_returns_generated_text_without_personal_info(self, mocked_post):
        mocked_post.return_value = ai_response(AI_TEXT)

        self.assertEqual(self.write(), AI_TEXT)
        payload = mocked_post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "test-model")
        self.assertIn("황금왕관 테루테루", payload["input"])
        self.assertIn("생일 일간 오행: 나무", payload["input"])
        self.assertIn("두 기운의 관계:", payload["input"])
        self.assertIn("완성 예시:", payload["instructions"])
        self.assertIn("하나만 본문에 한 번", payload["instructions"])
        self.assertNotIn("생년월일:", payload["input"])

    @override_settings(**AI_SETTINGS)
    @patch("fortune.services.fortune_writer.requests.post", side_effect=TimeoutError)
    def test_error_returns_none(self, _):
        self.assertIsNone(self.write())

    @override_settings(**AI_SETTINGS)
    @patch("fortune.services.fortune_writer.requests.post")
    def test_too_short_text_returns_none(self, mocked_post):
        mocked_post.return_value = ai_response("짧아요")
        self.assertIsNone(self.write())


@override_settings(**AI_SETTINGS)
class FortuneWithAITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(nickname="AI운세")
        self.profile = FortuneProfile.objects.create(
            user=self.user, calendar_type="SOLAR",
            birth_date="2002-05-17", converted_solar_date=date(2002, 5, 17),
            birth_time_unknown=True,
        )

    @patch("fortune.services.fortune_writer.requests.post")
    def test_today_result_uses_ai_text(self, mocked_post):
        mocked_post.return_value = ai_response(AI_TEXT)

        result = get_or_create_fortune_result(user=self.user, target_date=date(2026, 10, 30))

        self.assertEqual(result.detail_text, AI_TEXT)
        mocked_post.assert_called_once()

    @patch("fortune.services.fortune_writer.requests.post", side_effect=TimeoutError)
    def test_ai_failure_falls_back_to_rule_text(self, _):
        result = get_or_create_fortune_result(user=self.user, target_date=date(2026, 10, 30))

        self.assertTrue(result.detail_text.startswith(CHARACTERS[result.character].detail))

    @patch("fortune.services.fortune_writer.requests.post")
    def test_build_without_use_ai_never_calls_api(self, mocked_post):
        build_fortune_result(user=self.user, profile=self.profile, target_date=date(2026, 10, 30))
        mocked_post.assert_not_called()
