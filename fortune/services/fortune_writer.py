"""OpenAI로 오늘의 운세 상세 풀이를 자연스럽게 늘려 쓴다. 실패하면 None."""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

MIN_LENGTH = 200
MAX_LENGTH = 750

INSTRUCTIONS = (
    "당신은 날씨 사주 앱 WEE의 '오늘의 운세' 작가입니다. "
    "테루테루 캐릭터가 사용자에게 말을 거는 듯한 다정하고 귀여운 말투로 상세 풀이를 씁니다. "
    "입력으로 받은 생일 일간 오행과 오늘 일진 오행의 관계를 근거로, 오늘 하루의 흐름을 사주 관점에서 풀어주세요. "
    "핵심 흐름과 그 이유, 감정이나 대인관계에서 나타날 모습, 유리한 선택, 피하면 좋은 행동, 구체적인 실천 조언을 "
    "5~6문장, 350~550자로 이어서 쓰세요. 캐릭터 풀이를 그대로 복사하지 말고 의미만 활용하세요. "
    "행운 컬러·행운 아이템·행운 장소 중 문맥에 가장 잘 맞는 하나만 본문에 한 번 자연스럽게 활용하고, 나머지는 나열하지 마세요. "
    "날씨와 행운 행동이 주어지면 마지막 조언에 자연스럽게 연결하고, 날씨가 없으면 날씨를 추측하지 마세요. "
    "'오늘은 ~하니, ~해보는 거예요'처럼 부드러운 존댓말을 쓰되 같은 시작과 어미를 반복하지 마세요. "
    "입력에 없는 사주팔자, 태어난 시각, 대운이나 미래 사건을 만들어내지 마세요. "
    "불안하게 만드는 표현, 단정적인 예언, 건강·금전에 대한 확정적인 조언은 쓰지 마세요. "
    "사용자 이름, 생년월일, 나이, 오행 분석값 자체는 본문에 직접 언급하지 마세요. "
    "마크다운, 이모지, 따옴표, 제목 없이 한 문단의 본문만 출력하세요.\n\n"
    "완성 예시:\n"
    "마음속에만 두었던 일을 작게라도 시작하기 좋은 날이에요. 오늘의 흐름이 스스로 움직이려는 힘을 북돋아 주니, "
    "첫걸음을 내디디면 생각보다 자연스럽게 다음 순서가 보일 수 있어요. 사람들과 이야기할 때는 정답을 서둘러 내기보다 "
    "상대의 말을 한 번 더 들어주면 관계의 온도가 한결 부드러워질 거예요. 여러 일을 한꺼번에 벌이기보다는 가장 중요한 "
    "한 가지를 골라 끝까지 마무리해 보세요. 작은 노트에 떠오른 생각을 적어두면 놓치기 쉬운 힌트를 붙잡는 데 도움이 돼요. "
    "하늘이 맑다면 잠깐 햇빛을 쐬며 머릿속을 환기해보는 것도 오늘의 좋은 마무리가 될 거예요."
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
    target_date,
    birth_element_label: str,
    today_element_label: str,
    energy_relation: str,
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
        f"풀이 날짜: {target_date.isoformat()}",
        f"생일 일간 오행: {birth_element_label}",
        f"오늘 일진 오행: {today_element_label}",
        f"두 기운의 관계: {energy_relation}",
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
