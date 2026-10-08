import json
import logging
from typing import Any

import requests
from django.conf import settings


logger = logging.getLogger(__name__)


def _extract_output_text(response_data: dict) -> str:
    """LINER Responses API 응답에서 생성된 텍스트를 추출합니다."""

    for output_item in response_data.get("output", []):
        if output_item.get("type") != "message":
            continue

        for content_item in output_item.get("content", []):
            if content_item.get("type") == "output_text":
                text = content_item.get("text", "").strip()

                if text:
                    return text

    raise ValueError("LINER 응답에서 추천 문구를 찾지 못했습니다.")


def generate_notification_copy(
    *,
    notification_type: str,
    weather_context: dict[str, Any],
    fallback_title: str,
    fallback_body: str,
) -> tuple[str, str]:
    """
    날씨와 설문 정보를 바탕으로 짧은 푸시 알림 문구를 생성합니다.

    LINER가 비활성화되거나 호출에 실패하면
    기존 규칙 기반 문구를 그대로 반환합니다.
    """

    fallback = (fallback_title, fallback_body)

    if not settings.LINER_ENABLED:
        return fallback

    if not settings.LINER_API_KEY:
        logger.warning(
            "LINER_ENABLED=True이지만 LINER_API_KEY가 없습니다."
        )
        return fallback

    payload = {
        "model": settings.LINER_MODEL,
        "instructions": (
            "당신은 한국어 날씨 생활 알림 작성자입니다. "
            "제공된 날씨와 사용자 설정만 사용하세요. "
            "없는 정보를 추측하거나 과장하지 마세요. "
            "건강, 안전, 미래를 단정하지 마세요. "
            "친절하고 자연스러운 존댓말로 작성하세요. "
            "제목은 35자 이하, 본문은 100자 이하로 작성하세요."
        ),
        "input": (
            "다음 JSON 정보를 이용해 푸시 알림 문구를 작성하세요. "
            "반드시 지정된 JSON 형식으로만 응답하세요.\n"
            + json.dumps(
                {
                    "notificationType": notification_type,
                    "weather": weather_context,
                    "fallback": {
                        "title": fallback_title,
                        "body": fallback_body,
                    },
                },
                ensure_ascii=False,
            )
        ),
        "max_output_tokens": 180,
        "reasoning": {
            "effort": "low",
        },
        "text": {
            "format": {
                "type": "json_schema",
                "name": "weather_notification",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                        },
                        "body": {
                            "type": "string",
                        },
                    },
                    "required": [
                        "title",
                        "body",
                    ],
                    "additionalProperties": False,
                },
            },
        },
    }

    headers = {
        "Authorization": f"Bearer {settings.LINER_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            settings.LINER_API_URL,
            headers=headers,
            json=payload,
            timeout=settings.LINER_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        output_text = _extract_output_text(response.json())
        generated = json.loads(output_text)

        title = str(generated.get("title", "")).strip()
        body = str(generated.get("body", "")).strip()

        # 비어 있거나 지나치게 긴 문구는 푸시 알림에 사용하지 않습니다.
        if not title or not body:
            raise ValueError("LINER가 빈 추천 문구를 반환했습니다.")

        if len(title) > 35 or len(body) > 100:
            raise ValueError("LINER 추천 문구가 허용 길이를 초과했습니다.")

        return title, body

    except (
        requests.RequestException,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ):
        logger.exception(
            "LINER 문구 생성 실패: 기존 규칙 문구를 사용합니다."
        )
        return fallback