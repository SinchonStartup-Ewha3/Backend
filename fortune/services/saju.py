"""사주 원국과 오늘의 간지 관계를 계산한다.

운세 문구를 AI가 임의로 만들지 않도록 이 모듈에서 오행, 십신, 합충처럼
결정 가능한 값들을 먼저 계산한다. 날씨는 별도 계층에서 이 결과를 보정한다.
"""
import math
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

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

SEOUL_TZ = ZoneInfo("Asia/Seoul")

# 사주의 월주는 음력 초하루가 아니라 아래 12절이 드는 시점을 경계로 바뀐다.
# (절입 황경, 대략적인 양력 월·일, 인월부터의 월 인덱스)
MONTH_SOLAR_TERMS = (
    (285, 1, 6, 11),   # 소한 → 축월
    (315, 2, 4, 0),    # 입춘 → 인월
    (345, 3, 6, 1),    # 경칩 → 묘월
    (15, 4, 5, 2),     # 청명 → 진월
    (45, 5, 6, 3),     # 입하 → 사월
    (75, 6, 6, 4),     # 망종 → 오월
    (105, 7, 7, 5),    # 소서 → 미월
    (135, 8, 8, 6),    # 입추 → 신월
    (165, 9, 8, 7),    # 백로 → 유월
    (195, 10, 8, 8),   # 한로 → 술월
    (225, 11, 7, 9),   # 입동 → 해월
    (255, 12, 7, 10),  # 대설 → 자월
)

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


def _julian_day(moment: datetime) -> float:
    """UTC 시각을 역서 계산에 쓰는 율리우스일로 바꾼다."""
    moment = moment.astimezone(timezone.utc)
    year, month = moment.year, moment.month
    day = moment.day + (
        moment.hour
        + (moment.minute + (moment.second + moment.microsecond / 1_000_000) / 60) / 60
    ) / 24
    if month <= 2:
        year -= 1
        month += 12
    century = year // 100
    correction = 2 - century + century // 4
    return (
        math.floor(365.25 * (year + 4716))
        + math.floor(30.6001 * (month + 1))
        + day
        + correction
        - 1524.5
    )


def _sun_apparent_longitude(moment: datetime) -> float:
    """태양의 겉보기 황경을 도 단위로 계산한다.

    절입일 판정에 필요한 수준으로 NOAA/Meeus의 태양 위치 근사식을 사용한다.
    """
    centuries = (_julian_day(moment) - 2451545.0) / 36525
    mean_longitude = (
        280.46646 + centuries * (36000.76983 + 0.0003032 * centuries)
    ) % 360
    mean_anomaly = math.radians(
        357.52911 + centuries * (35999.05029 - 0.0001537 * centuries)
    )
    equation = (
        math.sin(mean_anomaly)
        * (1.914602 - centuries * (0.004817 + 0.000014 * centuries))
        + math.sin(2 * mean_anomaly) * (0.019993 - 0.000101 * centuries)
        + math.sin(3 * mean_anomaly) * 0.000289
    )
    true_longitude = mean_longitude + equation
    omega = math.radians(125.04 - 1934.136 * centuries)
    return (true_longitude - 0.00569 - 0.00478 * math.sin(omega)) % 360


def _longitude_delta(longitude: float, target: float) -> float:
    """목표 황경 전은 음수, 지난 뒤는 양수가 되도록 각도 차를 정규화한다."""
    return (longitude - target + 180) % 360 - 180


@lru_cache(maxsize=512)
def _solar_term_datetime(year: int, longitude: int, month: int, day: int) -> datetime:
    """해당 해의 절입 시각을 한국 표준시로 반환한다."""
    center = datetime(year, month, day, 12, tzinfo=SEOUL_TZ)
    lower = center - timedelta(days=4)
    upper = center + timedelta(days=4)
    if not (
        _longitude_delta(_sun_apparent_longitude(lower), longitude) <= 0
        <= _longitude_delta(_sun_apparent_longitude(upper), longitude)
    ):
        raise ValueError(f"{year}년 황경 {longitude}° 절입 시각을 찾지 못했습니다.")
    for _ in range(50):
        middle = lower + (upper - lower) / 2
        if _longitude_delta(_sun_apparent_longitude(middle), longitude) < 0:
            lower = middle
        else:
            upper = middle
    return upper.astimezone(SEOUL_TZ)


def _sexagenary_year_pillar(year: int) -> str:
    """서기 연도의 입춘 이후 년주를 반환한다. 1984년은 갑자년이다."""
    return STEMS[(year - 4) % 10] + BRANCHES[(year - 4) % 12]


def _solar_term_year_month_pillars(target: date) -> tuple[str, str]:
    """입춘과 12절 절입일을 기준으로 년주·월주를 계산한다.

    서비스의 일일 운세는 날짜 단위이므로 절입 시각이 포함된 한국 날짜 전체를
    새 월로 본다. 일주와 시주는 기존 ``korean_lunar_calendar`` 계산을 유지한다.
    """
    term_dates = [
        (_solar_term_datetime(target.year, longitude, month, day).date(), month_index)
        for longitude, month, day, month_index in MONTH_SOLAR_TERMS
    ]
    lichun_date = term_dates[1][0]
    pillar_year = target.year if target >= lichun_date else target.year - 1
    year_pillar = _sexagenary_year_pillar(pillar_year)

    # 소한 전은 전년도 대설부터 이어진 자월이다.
    month_index = 10
    for term_date, candidate_index in term_dates:
        if target >= term_date:
            month_index = candidate_index
        else:
            break

    # 갑·기년 병인, 을·경년 무인, 병·신년 경인,
    # 정·임년 임인, 무·계년 갑인에서 시작한다.
    year_stem_index = STEMS.index(year_pillar[0])
    first_month_stem_index = (year_stem_index % 5) * 2 + 2
    month_stem = STEMS[(first_month_stem_index + month_index) % 10]
    month_branch = BRANCHES[(2 + month_index) % 12]
    return year_pillar, month_stem + month_branch


def _gapja_pillars(target: date) -> list[str]:
    """양력 날짜의 절기 기준 년·월주와 기존 방식의 일주를 반환한다."""
    calendar = KoreanLunarCalendar()
    if not calendar.setSolarDate(target.year, target.month, target.day):
        raise ValueError(f"지원하지 않는 날짜입니다: {target.isoformat()}")
    words = calendar.getGapJaString().split()
    if len(words) < 3:
        raise ValueError("간지 정보를 해석하지 못했습니다.")
    year_pillar, month_pillar = _solar_term_year_month_pillars(target)
    day_pillar = words[2][:-1]
    return [year_pillar, month_pillar, day_pillar]


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
