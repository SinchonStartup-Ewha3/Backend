"""사주 원국과 오늘의 간지 관계를 계산한다.

운세 문구를 AI가 임의로 만들지 않도록 이 모듈에서 오행, 십신, 합충처럼
결정 가능한 값들을 먼저 계산한다. 날씨는 별도 계층에서 이 결과를 보정한다.
"""
from datetime import date, time

from django.db import models
from korean_lunar_calendar import KoreanLunarCalendar


class Element(models.TextChoices):
    WOOD = "WOOD", "나무"
    FIRE = "FIRE", "불"
    EARTH = "EARTH", "흙"
    METAL = "METAL", "쇠"
    WATER = "WATER", "물"


class LuckLevel(models.TextChoices):
    GREAT = "GREAT", "매우 좋은"
    GOOD = "GOOD", "좋은"
    NORMAL = "NORMAL", "무난한"
    CAUTION = "CAUTION", "조심해야 하는"
    BAD = "BAD", "안좋은"


# 천간(일간 첫 글자) → 오행
STEM_ELEMENT = {
    "갑": Element.WOOD, "을": Element.WOOD,
    "병": Element.FIRE, "정": Element.FIRE,
    "무": Element.EARTH, "기": Element.EARTH,
    "경": Element.METAL, "신": Element.METAL,
    "임": Element.WATER, "계": Element.WATER,
}

STEMS = tuple(STEM_ELEMENT)
BRANCHES = ("자", "축", "인", "묘", "진", "사", "오", "미", "신", "유", "술", "해")

BRANCH_ELEMENT = {
    "자": Element.WATER, "축": Element.EARTH,
    "인": Element.WOOD, "묘": Element.WOOD,
    "진": Element.EARTH, "사": Element.FIRE,
    "오": Element.FIRE, "미": Element.EARTH,
    "신": Element.METAL, "유": Element.METAL,
    "술": Element.EARTH, "해": Element.WATER,
}

# 양간은 0, 음간은 1로 비교한다.
STEM_POLARITY = {stem: index % 2 for index, stem in enumerate(STEMS)}

TEN_GOD_LABELS = {
    "FRIEND": "비견",
    "ROBBER": "겁재",
    "EATING_GOD": "식신",
    "HURTING_OFFICER": "상관",
    "INDIRECT_WEALTH": "편재",
    "DIRECT_WEALTH": "정재",
    "SEVEN_KILLINGS": "편관",
    "DIRECT_OFFICER": "정관",
    "INDIRECT_RESOURCE": "편인",
    "DIRECT_RESOURCE": "정인",
}

ELEMENT_SHORT_LABELS = {
    Element.WOOD: "목",
    Element.FIRE: "화",
    Element.EARTH: "토",
    Element.METAL: "금",
    Element.WATER: "수",
}

STEM_COMBINATIONS = {
    frozenset(pair) for pair in (("갑", "기"), ("을", "경"), ("병", "신"), ("정", "임"), ("무", "계"))
}
BRANCH_COMBINATIONS = {
    frozenset(pair) for pair in (("자", "축"), ("인", "해"), ("묘", "술"), ("진", "유"), ("사", "신"), ("오", "미"))
}
BRANCH_CLASHES = {
    frozenset(pair) for pair in (("자", "오"), ("축", "미"), ("인", "신"), ("묘", "유"), ("진", "술"), ("사", "해"))
}

# 상생: 키가 값을 낳는다 (목→화→토→금→수→목)
GENERATES = {
    Element.WOOD: Element.FIRE,
    Element.FIRE: Element.EARTH,
    Element.EARTH: Element.METAL,
    Element.METAL: Element.WATER,
    Element.WATER: Element.WOOD,
}

# 상극: 키가 값을 누른다 (목→토→수→화→금→목)
CONTROLS = {
    Element.WOOD: Element.EARTH,
    Element.EARTH: Element.WATER,
    Element.WATER: Element.FIRE,
    Element.FIRE: Element.METAL,
    Element.METAL: Element.WOOD,
}


def day_stem_element(target: date) -> Element:
    """그 날짜 일진의 천간 오행 (예: 경신일 → 경 → 쇠)"""
    calendar = KoreanLunarCalendar()
    calendar.setSolarDate(target.year, target.month, target.day)
    day_gapja = calendar.getGapJaString().split()[2]  # "경신일"
    return STEM_ELEMENT[day_gapja[0]]


def luck_level(my_element: Element, today_element: Element) -> LuckLevel:
    """나(생일 일간)와 오늘(일진)의 오행 관계로 운수 등급을 정한다."""
    if GENERATES[today_element] == my_element:   # 오늘이 나를 도와준다
        return LuckLevel.GREAT
    if today_element == my_element:              # 같은 기운
        return LuckLevel.GOOD
    if GENERATES[my_element] == today_element:   # 내가 기운을 내준다
        return LuckLevel.NORMAL
    if CONTROLS[my_element] == today_element:    # 내가 오늘을 눌러야 한다
        return LuckLevel.CAUTION
    return LuckLevel.BAD                         # 오늘이 나를 누른다


def helpful_element(my_element: Element) -> Element:
    """나를 도와주는(낳아주는) 오행. 행운 컬러·장소를 고를 때 쓴다."""
    for source, target in GENERATES.items():
        if target == my_element:
            return source
    raise ValueError(my_element)


def _gapja_pillars(target: date) -> list[str]:
    """양력 날짜의 년·월·일주를 두 글자 한글 간지로 반환한다."""
    calendar = KoreanLunarCalendar()
    if not calendar.setSolarDate(target.year, target.month, target.day):
        raise ValueError(f"지원하지 않는 날짜입니다: {target.isoformat()}")
    words = calendar.getGapJaString().split()
    if len(words) < 3:
        raise ValueError("간지 정보를 해석하지 못했습니다.")
    return [words[index][:-1] for index in range(3)]


def hour_branch_index(birth_time: time) -> int:
    """23~01시를 자시로 보는 두 시간 단위 시지 인덱스."""
    return ((birth_time.hour + 1) // 2) % 12


def hour_pillar(day_stem: str, birth_time: time) -> str:
    """일간과 시각으로 시주를 계산한다."""
    branch_index = hour_branch_index(birth_time)
    day_stem_index = STEMS.index(day_stem)
    # 갑·기일은 갑자, 을·경일은 병자, 병·신일은 무자,
    # 정·임일은 경자, 무·계일은 임자에서 시작한다.
    first_stem_index = (day_stem_index % 5) * 2
    stem = STEMS[(first_stem_index + branch_index) % 10]
    return stem + BRANCHES[branch_index]


def ten_god(day_stem: str, target_stem: str) -> str:
    """일간 기준 대상 천간의 십신 코드를 반환한다."""
    day_element = STEM_ELEMENT[day_stem]
    target_element = STEM_ELEMENT[target_stem]
    same_polarity = STEM_POLARITY[day_stem] == STEM_POLARITY[target_stem]

    if day_element == target_element:
        return "FRIEND" if same_polarity else "ROBBER"
    if GENERATES[day_element] == target_element:
        return "EATING_GOD" if same_polarity else "HURTING_OFFICER"
    if CONTROLS[day_element] == target_element:
        return "INDIRECT_WEALTH" if same_polarity else "DIRECT_WEALTH"
    if CONTROLS[target_element] == day_element:
        return "SEVEN_KILLINGS" if same_polarity else "DIRECT_OFFICER"
    return "INDIRECT_RESOURCE" if same_polarity else "DIRECT_RESOURCE"


def _pillar_dict(value: str) -> dict:
    return {
        "value": value,
        "stem": value[0],
        "branch": value[1],
        "stem_element": STEM_ELEMENT[value[0]].value,
        "branch_element": BRANCH_ELEMENT[value[1]].value,
    }


def _element_relation(day_element: Element, today_element: Element) -> dict:
    day_label = ELEMENT_SHORT_LABELS[day_element]
    today_label = ELEMENT_SHORT_LABELS[today_element]
    if day_element == today_element:
        return {"code": "SAME", "label": f"비화({day_label} 기운이 겹침)"}
    if GENERATES[today_element] == day_element:
        return {"code": "SUPPORTED", "label": f"상생({today_label}생{day_label})"}
    if GENERATES[day_element] == today_element:
        return {"code": "OUTPUT", "label": f"설기({day_label}생{today_label})"}
    if CONTROLS[day_element] == today_element:
        return {"code": "CONTROLS", "label": f"상극({day_label}극{today_label})"}
    return {"code": "CONTROLLED", "label": f"상극({today_label}극{day_label})"}


def analyze_daily_saju(*, birth_date: date, birth_time: time | None, target_date: date) -> dict:
    """사용자 원국과 목표 날짜의 기본 사주 신호를 직렬화 가능한 값으로 만든다.

    출생 시간이 없으면 시주만 제외하고 년·월·일주로 계산한다. 대운은 성별,
    절입 시각 등 추가 정책이 필요하므로 하루 상품의 점수에는 사용하지 않는다.
    """
    birth_values = _gapja_pillars(birth_date)
    if birth_time is not None:
        birth_values.append(hour_pillar(birth_values[2][0], birth_time))
    today_values = _gapja_pillars(target_date)

    natal_pillars = [_pillar_dict(value) for value in birth_values]
    today_pillars = [_pillar_dict(value) for value in today_values]
    day_stem = birth_values[2][0]
    today_day_stem = today_values[2][0]
    today_day_branch = today_values[2][1]
    day_element = STEM_ELEMENT[day_stem]
    today_day_element = STEM_ELEMENT[today_day_stem]

    elements = {element.value: 0 for element in Element}
    for pillar in natal_pillars:
        elements[pillar["stem_element"]] += 1
        elements[pillar["branch_element"]] += 1

    combinations = 0
    clashes = 0
    for pillar in natal_pillars:
        if frozenset((pillar["stem"], today_day_stem)) in STEM_COMBINATIONS:
            combinations += 1
        if frozenset((pillar["branch"], today_day_branch)) in BRANCH_COMBINATIONS:
            combinations += 1
        if frozenset((pillar["branch"], today_day_branch)) in BRANCH_CLASHES:
            clashes += 1

    daily_ten_gods = {
        "year": ten_god(day_stem, today_values[0][0]),
        "month": ten_god(day_stem, today_values[1][0]),
        "day": ten_god(day_stem, today_day_stem),
    }
    return {
        "day_stem": day_stem,
        "day_master_label": day_stem + ELEMENT_SHORT_LABELS[day_element],
        "day_element": day_element.value,
        "natal_pillars": natal_pillars,
        "today_pillars": today_pillars,
        "element_counts": elements,
        "daily_ten_gods": daily_ten_gods,
        "daily_ten_god_labels": {
            period: TEN_GOD_LABELS[code] for period, code in daily_ten_gods.items()
        },
        "combinations": combinations,
        "clashes": clashes,
        "day_element_relation": _element_relation(day_element, today_day_element),
        "birth_time_known": birth_time is not None,
    }
