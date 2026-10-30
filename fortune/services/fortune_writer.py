"""OpenAI로 오늘의 운세 상세 풀이를 자연스럽게 늘려 쓴다. 실패하면 None."""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

MIN_LENGTH = 120
MAX_LENGTH = 600

INSTRUCTIONS = (
    "당신은 날씨 사주 앱 WEE의 '오늘의 운세' 작가입니다. "
    "테루테루 캐릭터가 사용자에게 말을 거는 듯한 다정하고 귀여운 말투로 상세 풀이를 씁니다. "
    "'오늘은 ~하니, ~해보는 거예요'처럼 부드러운 존댓말을 쓰고, 같은 어미를 반복하지 마세요. "
    "입력으로 받은 캐릭터 풀이와 행운 행동의 의미를 유지하면서 4~5문장, 250~400자로 풀어 쓰세요. "
    "행운 컬러·행운 아이템·행운 장소를 각각 한 번씩 자연스럽게 넣으세요. "
    "날씨가 주어지면 날씨에 맞는 실용적인 팁을 한 가지 섞고, 날씨가 없으면 날씨 이야기는 하지 마세요. "
    "불안하게 만드는 표현, 단정적인 예언, 건강·금전에 대한 확정적인 조언은 쓰지 마세요. "
    "사용자 이름, 생년월일, 나이는 언급하지 마세요. "
    "마크다운, 이모지, 따옴표, 제목 없이 한 문단의 본문만 출력하세요."
)


def _extract_output_text(response_data: dict) -> str:
    for output_item in response_data.get("output", []):
        if output_item.get("type") != "message":
            continue
        for content_item in output_item.get("content", []):
            if content_item.get("type") == "output_text":
                text = str(content_item.get("text", "")).strip()
                if text:
                    return text
    raise ValueError("OpenAI 응답에서 문구를 찾지 못했습니다.")


def write_fortune_detail(
    *,
    character,
    luck_label: str,
    summary: str,
    weather_label: str | None,
    lucky_action: str | None,
) -> str | None:
    if not settings.OPENAI_FORTUNE_ENABLED:
        return None
    if not settings.OPENAI_API_KEY:
        logger.warning("OpenAI API 키가 없어 기본 운세 풀이를 사용합니다.")
        return None

    lines = [
        f"캐릭터: {character.name}",
        f"오늘의 운세 등급: {luck_label}",
        f"한 줄 요약: {summary}",
        f"캐릭터 풀이: {character.detail}",
        f"행운 컬러: {character.color}",
        f"행운 아이템: {character.item}",
        f"행운 장소: {character.place}",
        f"오늘 날씨: {weather_label or '알 수 없음'}",
    ]
    if lucky_action:
        lines.append(f"오늘의 행운 행동: {lucky_action}")

    payload = {
        "model": settings.OPENAI_FORTUNE_MODEL,
        "instructions": INSTRUCTIONS,
        "input": "\n".join(lines),
        "max_output_tokens": 700,
    }
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            settings.OPENAI_API_URL,
            headers=headers,
            json=payload,
            timeout=settings.OPENAI_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        text = " ".join(_extract_output_text(response.json()).split())
        if not MIN_LENGTH <= len(text) <= MAX_LENGTH:
            raise ValueError(f"운세 풀이 길이가 범위를 벗어났습니다: {len(text)}자")
        return text
    except Exception:
        logger.exception("OpenAI 운세 풀이 생성에 실패해 기본 풀이를 사용합니다.")
        return None