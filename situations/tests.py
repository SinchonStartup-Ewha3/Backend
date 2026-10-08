import requests
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from situations.services.liner_client import generate_notification_copy


class LinerNotificationCopyTests(SimpleTestCase):
    """LINER 문구 생성과 fallback 동작을 검증합니다."""

    @override_settings(
        LINER_ENABLED=False,
        LINER_API_KEY="",
    )
    @patch("situations.services.liner_client.requests.post")
    def test_returns_fallback_when_liner_is_disabled(
        self,
        mocked_post,
    ):
        result = generate_notification_copy(
            notification_type="OUTING_WEATHER",
            weather_context={
                "temperature": 12,
                "condition": "RAIN",
            },
            fallback_title="기본 제목",
            fallback_body="기본 내용",
        )

        self.assertEqual(
            result,
            ("기본 제목", "기본 내용"),
        )

        # 비활성화 상태에서는 LINER에 요청하면 안 됩니다.
        mocked_post.assert_not_called()

    @override_settings(
        LINER_ENABLED=True,
        LINER_API_KEY="test-api-key",
        LINER_API_URL="https://platform.liner.com/api/v1/responses",
        LINER_MODEL="liner-mark",
        LINER_TIMEOUT_SECONDS=10,
    )
    @patch("situations.services.liner_client.requests.post")
    def test_returns_generated_copy_when_liner_succeeds(
        self,
        mocked_post,
    ):
        mocked_response = mocked_post.return_value
        mocked_response.raise_for_status.return_value = None
        mocked_response.json.return_value = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": (
                                '{"title":"비 소식이 있어요",'
                                '"body":"외출할 때 우산을 챙겨주세요."}'
                            ),
                        }
                    ],
                }
            ]
        }

        result = generate_notification_copy(
            notification_type="OUTING_WEATHER",
            weather_context={
                "temperature": 12,
                "condition": "RAIN",
            },
            fallback_title="기본 제목",
            fallback_body="기본 내용",
        )

        self.assertEqual(
            result,
            (
                "비 소식이 있어요",
                "외출할 때 우산을 챙겨주세요.",
            ),
        )

        mocked_post.assert_called_once()

        # API Key가 요청 본문이 아닌 인증 헤더로 전달되는지 확인합니다.
        request_kwargs = mocked_post.call_args.kwargs

        self.assertEqual(
            request_kwargs["headers"]["Authorization"],
            "Bearer test-api-key",
        )

    @override_settings(
        LINER_ENABLED=True,
        LINER_API_KEY="test-api-key",
        LINER_API_URL="https://platform.liner.com/api/v1/responses",
        LINER_MODEL="liner-mark",
        LINER_TIMEOUT_SECONDS=10,
    )
    @patch(
        "situations.services.liner_client.requests.post",
        side_effect=requests.Timeout,
    )
    def test_returns_fallback_when_liner_fails(
        self,
        mocked_post,
    ):
        result = generate_notification_copy(
            notification_type="LAUNDRY",
            weather_context={
                "humidity": 80,
            },
            fallback_title="습도가 높아요",
            fallback_body="실내 건조를 추천해요.",
        )

        self.assertEqual(
            result,
            (
                "습도가 높아요",
                "실내 건조를 추천해요.",
            ),
        )

        mocked_post.assert_called_once()