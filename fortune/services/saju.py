"""생년월일과 오늘 날짜의 일진(갑자)으로 오행 관계를 계산한다."""
from datetime import date

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