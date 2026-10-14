import hashlib
import logging

from core.constants import WeatherCondition
from fortune.models import FortuneResult

from .saju import (
    Element,
    LuckLevel,
    day_stem_element,
    helpful_element,
    luck_level,
)

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

RELATION_SENTENCES = {
    LuckLevel.GREAT: "오늘의 기운이 당신을 든든하게 받쳐 주니, 미뤄 둔 일을 시작해 보세요.",
    LuckLevel.GOOD: "오늘은 당신과 닮은 기운이 흐르는 날이라 평소 하던 대로가 가장 좋습니다.",
    LuckLevel.NORMAL: "당신의 기운을 나눠 주는 날이니 무리한 약속은 줄이는 게 좋습니다.",
    LuckLevel.CAUTION: "작은 일에 힘이 많이 드는 날이니 중요한 결정은 한 번 더 확인하세요.",
    LuckLevel.BAD: "기운이 눌리기 쉬운 날이니 말과 지출을 조심하고 일찍 쉬어 주세요.",
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

# 나를 도와주는 오행 → 행운 컬러·장소 후보
ELEMENT_COLORS = {
    Element.WOOD: ["초록", "민트", "올리브"],
    Element.FIRE: ["코랄", "레드", "오렌지"],
    Element.EARTH: ["베이지", "머스터드", "브라운"],
    Element.METAL: ["화이트", "실버", "아이보리"],
    Element.WATER: ["네이비", "블랙", "딥블루"],
}
ELEMENT_PLACES = {
    Element.WOOD: ["공원", "식물원", "산책로"],
    Element.FIRE: ["카페", "영화관", "전시회"],
    Element.EARTH: ["베이커리", "시장", "도서관"],
    Element.METAL: ["서점", "문구점", "편집숍"],
    Element.WATER: ["강변", "수영장", "서점"],
}
# 오늘 날씨 → 행운 아이템 후보 (날씨를 모르면 기본 후보)
WEATHER_ITEMS = {
    WeatherCondition.RAIN: ["투명우산", "레인부츠", "방수 파우치"],
    WeatherCondition.SHOWER: ["접이식 우산", "손수건", "바람막이"],
    WeatherCondition.SLEET: ["털장갑", "목도리", "미끄럼 방지 신발"],
    WeatherCondition.SNOW: ["털장갑", "목도리", "핫팩"],
    WeatherCondition.CLEAR: ["선글라스", "모자", "텀블러"],
    WeatherCondition.PARTLY_CLOUDY: ["이어폰", "가디건", "텀블러"],
    WeatherCondition.CLOUDY: ["향수", "머그컵", "가디건"],
}
DEFAULT_ITEMS = ["손수건", "텀블러", "이어폰"]


def _pick(options, seed: str):
    """같은 사람·같은 날짜면 항상 같은 항목을 고른다."""
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return options[int(digest, 16) % len(options)]


def _with_particle(word: str) -> str:
    """받침 유무에 맞춰 '과/와'를 붙인다 (물과, 나무와)"""
    has_final = (ord(word[-1]) - 0xAC00) % 28 != 0
    return f"{word}{'과' if has_final else '와'}"


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
    helper = Element(helpful_element(my_element))
    seed = f"{user.pk}:{target_date.isoformat()}"

    items = WEATHER_ITEMS.get(weather, DEFAULT_ITEMS)
    detail_lines = [
        f"오늘 당신의 기운은 '{_with_particle(helper.label)}' 맞닿아 있습니다.",
        RELATION_SENTENCES[level],
    ]
    if weather in WEATHER_SENTENCES:
        detail_lines.append(WEATHER_SENTENCES[weather])

    return {
        "title": f"오늘 운수 {level.label} 테루테루",
        "luck_level": level.value,
        "summary": SUMMARIES[level],
        "weather_condition": weather,
        "lucky_color": _pick(ELEMENT_COLORS[helper], seed + ":color"),
        "lucky_item": _pick(items, seed + ":item"),
        "lucky_place": _pick(ELEMENT_PLACES[helper], seed + ":place"),
        "detail_text": "\n".join(detail_lines),
    }


def get_or_create_fortune_result(*, user, target_date, profile=None):
    """무료 요약과 결제 후 상세풀이가 공유하는 날짜별 결과를 반환합니다.

    하루에 한 번만 만들어 저장하므로, 처음 조회한 시점의 날씨로 고정된다.
    """
    existing = FortuneResult.objects.filter(user=user, target_date=target_date).first()
    if existing is not None:
        return existing

    profile = profile or user.fortune_profile
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