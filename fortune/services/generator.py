import hashlib
import logging

from core.constants import WeatherCondition
from fortune.models import FortuneResult

from .characters import CHARACTERS, CHARACTERS_BY_LEVEL
from .saju import LuckLevel, day_stem_element, luck_level

logger = logging.getLogger(__name__)

WEATHER_LABELS = {
    WeatherCondition.CLEAR: "맑은 하루",
    WeatherCondition.PARTLY_CLOUDY: "구름 조금 낀 하루",
    WeatherCondition.CLOUDY: "흐린 하루",
    WeatherCondition.RAIN: "비오는 하루",
    WeatherCondition.SHOWER: "소나기 오는 하루",
    WeatherCondition.SLEET: "진눈깨비 내리는 하루",
    WeatherCondition.SNOW: "눈오는 하루",
}

SUMMARIES = {
    LuckLevel.GREAT: "오늘은 아주 멋진 날이 기대될 예정입니다",
    LuckLevel.GOOD: "기분 좋은 일이 하나쯤 찾아올 거예요",
    LuckLevel.NORMAL: "잔잔하게 흘러가는 편안한 하루예요",
    LuckLevel.CAUTION: "서두르지 않으면 무난히 지나갈 거예요",
    LuckLevel.BAD: "오늘은 한 박자 쉬어 가는 게 좋아요",
}

WEATHER_SENTENCES = {
    WeatherCondition.RAIN: "비가 오는 날일수록 차분하게 움직이면 운이 따릅니다.",
    WeatherCondition.SHOWER: "갑자기 바뀌는 날씨처럼 계획도 유연하게 가져가 보세요.",
    WeatherCondition.SLEET: "길이 미끄러운 날이니 발걸음을 천천히 옮기세요.",
    WeatherCondition.SNOW: "눈 오는 날의 고요함이 마음을 정리하는 데 도움이 됩니다.",
    WeatherCondition.CLEAR: "맑은 햇살 아래 잠깐 걷는 시간이 행운을 불러옵니다.",
    WeatherCondition.PARTLY_CLOUDY: "가볍게 바깥 공기를 쐬면 생각이 정리됩니다.",
    WeatherCondition.CLOUDY: "흐린 날엔 따뜻한 음료 한 잔이 기분을 바꿔 줍니다.",
}


def _pick(options, seed: str):
    """같은 사람·같은 날짜면 항상 같은 항목을 고른다."""
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return options[int(digest, 16) % len(options)]


def get_today_weather(user) -> str | None:
    """사용자 위치의 현재 날씨 상태. 위치가 없거나 기상청 오류면 None"""
    from home.services.weather import get_current_weather, get_user_grid

    grid = get_user_grid(user)
    if grid is None:
        return None
    try:
        return get_current_weather(*grid)["condition"]
    except Exception:
        logger.warning("운세용 날씨 조회에 실패해 날씨 없이 생성합니다.", exc_info=True)
        return None


def build_fortune_result(*, user, profile, target_date, weather=None):
    """생일 일간과 오늘 일진의 오행 관계 + 오늘 날씨로 운세를 만든다."""
    my_element = day_stem_element(profile.converted_solar_date)
    today_element = day_stem_element(target_date)
    level = LuckLevel(luck_level(my_element, today_element))
    seed = f"{user.pk}:{target_date.isoformat()}"

    character = CHARACTERS[_pick(CHARACTERS_BY_LEVEL[level], seed + ":character")]
    detail_lines = [character.detail]
    if weather in WEATHER_SENTENCES:
        detail_lines.append(WEATHER_SENTENCES[weather])

    return {
        "character": character.code,
        "title": character.name,
        "luck_level": level.value,
        "summary": SUMMARIES[level],
        "weather_condition": weather,
        "lucky_color": character.color,
        "lucky_item": character.item,
        "lucky_place": character.place,
        "detail_text": "\n".join(detail_lines),
    }


def is_legacy_result(result) -> bool:
    """예전 로직으로 만든 결과인지 (요약 문구나 캐릭터가 비어 있음)"""
    return not result.summary or not result.character


def refresh_legacy_result(result, *, profile, weather=None):
    """예전 결과를 새 로직으로 다시 계산해 덮어쓴다. 저장된 날씨가 있으면 그대로 쓴다."""
    if result.weather_condition:
        weather = result.weather_condition
    data = build_fortune_result(
        user=result.user,
        profile=profile,
        target_date=result.target_date,
        weather=weather,
    )
    for field, value in data.items():
        setattr(result, field, value)
    result.save(update_fields=list(data))
    return result


def get_or_create_fortune_result(*, user, target_date, profile=None):
    """무료 요약과 결제 후 상세풀이가 공유하는 날짜별 결과를 반환합니다.

    하루에 한 번만 만들어 저장하므로, 처음 조회한 시점의 날씨로 고정된다.
    새 로직 이전에 만든 임시 결과가 있으면 다시 계산한다.
    """
    existing = FortuneResult.objects.filter(user=user, target_date=target_date).first()
    if existing is not None and not is_legacy_result(existing):
        return existing

    profile = profile or user.fortune_profile
    if existing is not None:
        return refresh_legacy_result(
            existing, profile=profile, weather=get_today_weather(user),
        )

    result, _ = FortuneResult.objects.get_or_create(
        user=user,
        target_date=target_date,
        defaults=build_fortune_result(
            user=user,
            profile=profile,
            target_date=target_date,
            weather=get_today_weather(user),
        ),
    )
    return result