import hashlib
import logging

from django.conf import settings

from core.constants import WeatherCondition
from fortune.models import FortuneResult

from .characters import CHARACTERS, CHARACTERS_BY_LEVEL
from .campus_fortune import build_campus_fortunes
from .fortune_writer import write_fortune_detail
from .lucky_actions import CATEGORY_LABELS, pick_lucky_action, weather_category
from .saju import LuckLevel, analyze_daily_saju, day_stem_element, luck_level

logger = logging.getLogger(__name__)

ENERGY_RELATIONS = {
    LuckLevel.GREAT: "오늘의 기운이 사용자의 기운을 북돋는 상생 흐름",
    LuckLevel.GOOD: "같은 기운이 겹쳐 장점과 추진력이 또렷해지는 흐름",
    LuckLevel.NORMAL: "사용자의 기운이 오늘의 흐름으로 흘러가 에너지를 바깥에 쓰기 쉬운 흐름",
    LuckLevel.CAUTION: "사용자가 오늘의 기운을 조율해야 하므로 힘을 분산하지 않는 것이 중요한 흐름",
    LuckLevel.BAD: "오늘의 기운이 사용자의 기운을 누를 수 있어 속도를 조절하고 균형을 지키는 흐름",
}

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

def _pick(options, seed: str):
    """같은 사람·같은 날짜면 항상 같은 항목을 고른다."""
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return options[int(digest, 16) % len(options)]


def _user_region(user):
    """저장 지역이 없는 GPS 사용자는 마지막 좌표에서 가장 가까운 동을 쓴다."""
    if user.region is not None:
        return user.region
    if user.last_lat is None or user.last_lng is None:
        return None
    from core.geo import find_nearest_region

    return find_nearest_region(float(user.last_lat), float(user.last_lng))


def get_today_weather(user) -> dict | None:
    """사용자 위치의 현재 날씨. 위치가 없거나 기상청 오류면 None"""
    from home.services.weather import get_current_weather, get_user_grid

    grid = get_user_grid(user)
    if grid is None:
        return None
    try:
        weather = get_current_weather(*grid, include_hourly=True)
    except Exception:
        logger.warning("운세용 날씨 조회에 실패해 날씨 없이 생성합니다.", exc_info=True)
        return None

    # 기존 에어코리아 데이터를 함께 넣어 미세먼지가 나쁜 날의 행동을 고른다.
    try:
        from situations.services.airkorea import get_air_quality

        air_quality = get_air_quality(_user_region(user)) if settings.KMA_SERVICE_KEY else None
        if air_quality:
            weather["airQuality"] = air_quality
    except Exception:
        logger.warning("운세용 미세먼지 조회에 실패해 날씨 정보만 사용합니다.", exc_info=True)
    return weather


def _as_weather(weather) -> dict | None:
    """날씨 상태 문자열('RAIN')이나 현재 날씨 dict를 dict로 맞춘다."""
    if not weather:
        return None
    if isinstance(weather, str):
        return {"condition": weather}
    return weather


def build_fortune_result(*, user, profile, target_date, weather=None, use_ai=False):
    """생일 일간과 오늘 일진의 오행 관계 + 오늘 날씨로 운세를 만든다.

    use_ai=True면 OpenAI로 상세 풀이를 늘려 쓰고, 실패하면 규칙 기반 풀이를 쓴다.
    """
    weather = _as_weather(weather)
    my_element = day_stem_element(profile.converted_solar_date)
    today_element = day_stem_element(target_date)
    level = LuckLevel(luck_level(my_element, today_element))
    seed = f"{user.pk}:{target_date.isoformat()}"

    character = CHARACTERS[_pick(CHARACTERS_BY_LEVEL[level], seed + ":character")]
    category = weather_category(weather)
    lucky_action = pick_lucky_action(category, seed)
    saju_analysis = analyze_daily_saju(
        birth_date=profile.converted_solar_date,
        birth_time=None if profile.birth_time_unknown else profile.birth_time,
        target_date=target_date,
    )
    category_fortunes = build_campus_fortunes(
        analysis=saju_analysis,
        weather=weather,
    )

    detail_text = " ".join(line for line in [character.detail, lucky_action] if line)
    if use_ai:
        detail_text = write_fortune_detail(
            character=character,
            luck_label=level.label,
            summary=SUMMARIES[level],
            target_date=target_date,
            birth_element_label=my_element.label,
            today_element_label=today_element.label,
            energy_relation=ENERGY_RELATIONS[level],
            weather_label=CATEGORY_LABELS.get(category),
            lucky_action=lucky_action,
        ) or detail_text

    return {
        "character": character.code,
        "title": character.name,
        "luck_level": level.value,
        "summary": SUMMARIES[level],
        "weather_condition": weather["condition"] if weather else None,
        "weather_snapshot": weather or {},
        "saju_analysis": saju_analysis,
        "category_fortunes": category_fortunes,
        "lucky_color": character.color,
        "lucky_item": character.item,
        "lucky_place": character.place,
        "detail_text": detail_text,
    }


def is_legacy_result(result) -> bool:
    """새 계산 필드 중 채워지지 않은 값이 있는 결과인지 확인한다."""
    return not all((
        result.summary,
        result.character,
        result.saju_analysis,
        result.category_fortunes,
    ))


def refresh_legacy_result(result, *, profile, weather=None, use_ai=False):
    """결과가 만들어진 세대에 맞춰 전체 재계산 또는 빈 필드 보완을 수행한다.

    summary나 character가 없는 구형 결과는 캐릭터와 문구가 한 세트로 맞도록
    전체를 다시 계산한다. 두 값이 모두 있는 결과는 기존 OpenAI 상세 풀이와
    행운 정보를 보존하고 새 계산 필드 중 빈 값만 채운다.
    """
    requires_full_refresh = not result.summary or not result.character
    if result.weather_snapshot:
        weather = result.weather_snapshot
    elif result.weather_condition:
        weather = result.weather_condition
    data = build_fortune_result(
        user=result.user,
        profile=profile,
        target_date=result.target_date,
        weather=weather,
        use_ai=use_ai if requires_full_refresh else use_ai and not result.detail_text,
    )
    if requires_full_refresh:
        for field, value in data.items():
            setattr(result, field, value)
        result.save(update_fields=list(data))
        return result

    empty_values = (None, "", [], {})
    update_fields = []
    for field, value in data.items():
        if getattr(result, field) in empty_values:
            setattr(result, field, value)
            update_fields.append(field)
    if update_fields:
        result.save(update_fields=update_fields)
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
            existing, profile=profile, weather=get_today_weather(user), use_ai=True,
        )

    result, _ = FortuneResult.objects.get_or_create(
        user=user,
        target_date=target_date,
        defaults=build_fortune_result(
            user=user,
            profile=profile,
            target_date=target_date,
            weather=get_today_weather(user),
            use_ai=True,
        ),
    )
    return result