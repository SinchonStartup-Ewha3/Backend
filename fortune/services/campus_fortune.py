"""사주 신호와 실제 날씨를 운세 결과 화면의 4개 카테고리와 '오늘의 한 줄'로 번역한다."""
import hashlib
from datetime import datetime, time

from .saju import LuckLevel, hour_pillar, ten_god


CATEGORY_DEFINITIONS = {
    "WORK": {
        "label": "업무운",
        "weights": {
            "DIRECT_RESOURCE": 10, "DIRECT_OFFICER": 9, "INDIRECT_RESOURCE": 7,
            "EATING_GOD": 7, "HURTING_OFFICER": -2, "ROBBER": -3,
        },
    },
    "LOVE": {
        "label": "연애운",
        "weights": {
            "DIRECT_WEALTH": 9, "INDIRECT_WEALTH": 8,
            "DIRECT_OFFICER": 9, "SEVEN_KILLINGS": 6,
            "EATING_GOD": 6, "HURTING_OFFICER": 4,
        },
    },
    "MONEY": {
        "label": "금전운",
        "weights": {
            "DIRECT_WEALTH": 13, "INDIRECT_WEALTH": 10,
            "EATING_GOD": 6, "DIRECT_OFFICER": 3,
            "ROBBER": -11, "HURTING_OFFICER": -3,
        },
    },
    "HEALTH": {
        "label": "건강운",
        "weights": {
            "FRIEND": 9, "EATING_GOD": 7, "DIRECT_RESOURCE": 6,
            "INDIRECT_RESOURCE": 4, "SEVEN_KILLINGS": -7,
            "HURTING_OFFICER": -2,
        },
    },
}
CATEGORY_CODES = tuple(CATEGORY_DEFINITIONS)

MIN_SCORE, MAX_SCORE = 40, 95
PERIOD_WEIGHT = {"year": 0.35, "month": 0.65, "day": 1.0}
WET_CONDITIONS = {"RAIN", "SHOWER", "SLEET", "SNOW"}
ELEMENT_NAMES = {
    "WOOD": "목",
    "FIRE": "화",
    "EARTH": "토",
    "METAL": "금",
    "WATER": "수",
}

TEN_GOD_EFFECTS = {
    "FRIEND": "내 페이스를 지키는 비견 기운",
    "ROBBER": "경쟁과 즉흥성이 커지는 겁재 기운",
    "EATING_GOD": "꾸준히 결과를 만드는 식신 기운",
    "HURTING_OFFICER": "표현과 문제의식이 또렷한 상관 기운",
    "INDIRECT_WEALTH": "변화에 빠르게 대응하는 편재 기운",
    "DIRECT_WEALTH": "계획과 자원 관리에 강한 정재 기운",
    "SEVEN_KILLINGS": "긴장과 압박을 추진력으로 바꾸는 편관 기운",
    "DIRECT_OFFICER": "순서와 책임을 중시하는 정관 기운",
    "INDIRECT_RESOURCE": "새로운 관점을 떠올리는 편인 기운",
    "DIRECT_RESOURCE": "배움과 정리에 유리한 정인 기운",
}

MONEY_FLOW_MESSAGES = {
    "FRIEND": "오늘은 비견 기운이 들어와 내 기준대로 돈을 쓰고 싶은 마음이 커질 수 있어요.",
    "ROBBER": "오늘은 겁재 기운이 들어와 어울리는 자리에서 예상 밖의 지출이 늘기 쉬워요.",
    "EATING_GOD": "오늘은 식신 기운이 들어와 맛있는 음식이나 소소한 즐거움에 돈을 쓰고 싶어져요.",
    "HURTING_OFFICER": "오늘은 상관 기운이 들어와 기분 전환을 위한 즉흥적인 소비가 생기기 쉬워요.",
    "INDIRECT_WEALTH": "오늘은 편재 기운이 들어와 예상하지 못한 소비와 작은 기회가 함께 들어올 수 있어요.",
    "DIRECT_WEALTH": "오늘은 정재 기운이 들어와 돈을 계획적으로 관리하려는 마음이 커지는 날이에요.",
    "SEVEN_KILLINGS": "오늘은 편관 기운의 압박 때문에 편의를 위해 돈으로 해결하고 싶은 마음이 커질 수 있어요.",
    "DIRECT_OFFICER": "오늘은 정관 기운이 들어와 꼭 필요한 지출과 불필요한 지출을 구분하기 좋아요.",
    "INDIRECT_RESOURCE": "오늘은 편인 기운이 들어와 새로운 취미나 콘텐츠에 호기심 지출이 생길 수 있어요.",
    "DIRECT_RESOURCE": "오늘은 정인 기운이 들어와 공부나 자기계발을 위한 지출에 마음이 기울기 쉬워요.",
}

CATEGORY_ACTIONS = {
    "WORK": "가장 중요한 일 하나를 25분만 먼저 시작해보세요.",
    "LOVE": "안부와 함께 답하기 쉬운 질문 하나를 보내보세요.",
    "MONEY": "오늘 사용할 금액의 상한을 먼저 정해두세요.",
    "HEALTH": "물을 마시고 10분 정도 가볍게 걸어보세요.",
}

CATEGORY_REASON_TEMPLATES = {
    "WORK": "오늘은 {day_effect}이 들어오는 날이에요. {direction}",
    "LOVE": "{relationship_signal} {direction}",
    "MONEY": "{money_flow} {direction}",
    "HEALTH": "{element_intro}, {energy_flow}",
}

CATEGORY_DIRECTIONS = {
    "WORK": (
        "중요한 일을 먼저 잡아도 흐름이 잘 받쳐줘요.",
        "범위를 줄이고 한 가지씩 끝내는 편이 좋아요.",
    ),
    "LOVE": (
        "가볍게 먼저 연락하며 분위기를 열어도 좋아요.",
        "상대의 반응을 빠르게 단정하지 않는 편이 좋아요.",
    ),
    "MONEY": (
        "계획한 소비는 괜찮지만 결제 전에 목적을 한 번 확인해보세요.",
        "편의를 위한 작은 결제가 겹치지 않도록 한도를 정해두는 게 좋아요.",
    ),
    "HEALTH": ("", ""),
}

# 점 개수(1~5) 구간별 카드 제목 후보. 사람·날짜가 같으면 항상 같은 문구가 나온다.
CATEGORY_HEADLINES = {
    "WORK": {
        "HIGH": ("손대는 일마다 속도가 붙는 날", "미뤄둔 일을 끝내기 좋은 날"),
        "MID": ("한 가지에 집중하면 풀리는 날", "순서만 정하면 무난한 날"),
        "LOW": ("서두르면 놓치는 날", "확인 한 번이 실수를 막는 날"),
    },
    "LOVE": {
        "HIGH": ("먼저 건넨 말이 통하는 날", "마음이 자연스럽게 닿는 날"),
        "MID": ("말보다 타이밍이 중요한 날", "작은 표현이 분위기를 바꾸는 날"),
        "LOW": ("반응을 서둘러 해석하지 말 날", "한 박자 쉬어 가면 편한 날"),
    },
    "MONEY": {
        "HIGH": ("계획한 소비가 만족으로 돌아오는 날", "작은 기회를 알아보기 좋은 날"),
        "MID": ("필요와 욕심을 나누면 무난한 날", "영수증을 한 번 더 보는 날"),
        "LOW": ("충동은 날씨 탓입니다", "작은 결제가 쌓이기 쉬운 날"),
    },
    "HEALTH": {
        "HIGH": ("몸이 가볍게 움직여주는 날", "컨디션이 받쳐주는 날"),
        "MID": ("쉬는 리듬만 챙기면 괜찮은 날", "물 한 잔이 힘이 되는 날"),
        "LOW": ("몸이 날씨를 먼저 느끼는 날", "무리하지 않는 게 이기는 날"),
    },
}

ENERGY_FLOW_MESSAGES = {
    "SUPPORTED": "나를 도와주는 흐름이라 에너지가 자연스럽게 채워지는 날이에요.",
    "SAME": "나와 비슷한 기운이 겹쳐 평소의 힘이 또렷해지는 날이에요.",
    "OUTPUT": "내 기운이 바깥으로 많이 흐르는 날이라 활동한 만큼 쉽게 지칠 수 있어요.",
    "CONTROLS": "주변을 직접 정리해야 해서 생각보다 에너지를 많이 쓰게 될 수 있어요.",
    "CONTROLLED": "오늘의 기운이 나를 조금 누르는 흐름이라 서두르면 평소보다 쉽게 지칠 수 있어요.",
}

# '오늘의 한 줄' 제목: 운세 등급 × 비·눈 여부
DAILY_TITLES = {
    LuckLevel.GREAT: {
        "WET": "비가 와도 오늘의 흐름은 당신 편입니다.",
        "DRY": "오늘은 망설이기보다 한 발 먼저 나서는 날입니다.",
    },
    LuckLevel.GOOD: {
        "WET": "빗소리처럼 꾸준히 이어가면 좋은 일이 닿는 날입니다.",
        "DRY": "가볍게 시작한 일이 기분 좋게 이어지는 날입니다.",
    },
    LuckLevel.NORMAL: {
        "WET": "오늘은 서두르기보다 흐름을 따라가는 날입니다.",
        "DRY": "잔잔한 흐름 속에서 내 속도를 지키는 날입니다.",
    },
    LuckLevel.CAUTION: {
        "WET": "오늘은 멀리 가기보다 발밑을 살피는 날입니다.",
        "DRY": "한 번 더 확인하면 무난히 지나가는 날입니다.",
    },
    LuckLevel.BAD: {
        "WET": "오늘은 나아가기보다 젖지 않게 지키는 날입니다.",
        "DRY": "오늘은 나아가기보다 나를 지키는 날입니다.",
    },
}

DAILY_BODIES = {
    LuckLevel.GREAT: "{color} 색을 곁에 두고, 미뤄둔 일 하나를 오늘 시작해보는 건 어떨까요?",
    LuckLevel.GOOD: "{color} 색을 곁에 두고, 떠오른 사람에게 먼저 안부를 건네보는 건 어떨까요?",
    LuckLevel.NORMAL: "{color} 색을 곁에 두고, 해야 할 일 하나만 골라 마무리해보는 건 어떨까요?",
    LuckLevel.CAUTION: "{color} 색을 곁에 두고, 결정하기 전에 한 번만 더 살펴보는 건 어떨까요?",
    LuckLevel.BAD: "{color} 색을 곁에 두고, 속도를 한 템포만 낮춰보는 건 어떨까요?",
}


def _pick(options, seed: str):
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return options[int(digest, 16) % len(options)]


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _hourly(weather: dict | None) -> list[dict]:
    return list((weather or {}).get("hourly") or [])


def _is_wet(item: dict) -> bool:
    probability = _number(item.get("precipitationProbability")) or 0
    return item.get("condition") in WET_CONDITIONS or probability >= 60


def _rain_expected(weather: dict | None) -> bool:
    if not weather:
        return False
    return weather.get("condition") in WET_CONDITIONS or any(
        _is_wet(item) for item in _hourly(weather)
    )


def _air_is_bad(weather: dict | None) -> bool:
    air = (weather or {}).get("airQuality") or {}
    return (
        air.get("grade") in {"BAD", "VERY_BAD"}
        or (_number(air.get("pm10")) or 0) > 80
        or (_number(air.get("pm25")) or 0) > 35
    )


def _weather_modifiers(weather: dict | None) -> dict[str, int]:
    result = {code: 0 for code in CATEGORY_DEFINITIONS}
    if not weather:
        return result

    humidity = _number(weather.get("humidity"))
    feels_like = _number(weather.get("feelsLike"))
    wind = _number(weather.get("windSpeed"))
    minimum = _number(weather.get("minTemperature"))
    maximum = _number(weather.get("maxTemperature"))

    if humidity is not None and humidity >= 80:
        result["WORK"] -= 3
        result["HEALTH"] -= 4
    if feels_like is not None and (feels_like <= 0 or feels_like >= 30):
        result["HEALTH"] -= 6
        result["WORK"] -= 2
    if wind is not None and wind >= 7:
        result["WORK"] -= 3
    if minimum is not None and maximum is not None and maximum - minimum >= 10:
        result["HEALTH"] -= 3
    if _rain_expected(weather):
        result["MONEY"] -= 4
        result["WORK"] -= 4
    if _air_is_bad(weather):
        result["HEALTH"] -= 6
    return result


def _category_score(code: str, analysis: dict, weather: dict | None) -> int:
    definition = CATEGORY_DEFINITIONS[code]
    score = 68.0
    for period, god in analysis["daily_ten_gods"].items():
        score += definition["weights"].get(god, 0) * PERIOD_WEIGHT[period]
    score += min(analysis["combinations"], 2) * (5 if code == "LOVE" else 2)
    score -= min(analysis["clashes"], 2) * (6 if code == "LOVE" else 3)
    score += _weather_modifiers(weather)[code]
    return max(MIN_SCORE, min(MAX_SCORE, round(score)))


def score_to_dots(score: int) -> int:
    """40~95점을 화면의 점 5개 중 채워질 개수(1~5)로 바꾼다."""
    return 1 + round((score - MIN_SCORE) / (MAX_SCORE - MIN_SCORE) * 4)


def _headline(code: str, dots: int, seed: str) -> str:
    tier = "HIGH" if dots >= 4 else "MID" if dots == 3 else "LOW"
    return _pick(CATEGORY_HEADLINES[code][tier], f"{seed}:{code}:headline")


def _format_hour(item: dict | None) -> str | None:
    if not item:
        return None
    try:
        hour = datetime.fromisoformat(item["time"]).hour
    except (KeyError, TypeError, ValueError):
        hour = int(item.get("hour", 0))
    suffix = "오전" if hour < 12 else "오후"
    display = hour if 1 <= hour <= 12 else abs(hour - 12) or 12
    return f"{suffix} {display}시 전후"


def _best_time(code: str, analysis: dict, weather: dict | None) -> str:
    candidates = []
    today_stem = analysis["today_pillars"][2]["stem"]
    user_stem = analysis["day_stem"]
    weights = CATEGORY_DEFINITIONS[code]["weights"]
    for item in _hourly(weather):
        try:
            dt = datetime.fromisoformat(item["time"])
        except (KeyError, TypeError, ValueError):
            continue
        if not 8 <= dt.hour <= 21:
            continue
        hour_god = ten_god(user_stem, hour_pillar(today_stem, time(dt.hour))[0])
        value = weights.get(hour_god, 0)
        if _is_wet(item):
            value -= 2
        humidity = _number(item.get("humidity"))
        if humidity is not None and humidity >= 85 and code in {"WORK", "HEALTH"}:
            value -= 3
        candidates.append((value, item))
    if not candidates:
        return {
            "WORK": "오전 10시~낮 12시",
            "LOVE": "오후 1시~3시",
            "MONEY": "점심 결제 전",
            "HEALTH": "오전 9시~11시",
        }[code]
    return _format_hour(max(candidates, key=lambda row: row[0])[1])


def _rain_start(weather: dict | None) -> str | None:
    return _format_hour(next((item for item in _hourly(weather) if _is_wet(item)), None))


def _air_message(weather: dict) -> str:
    air = weather.get("airQuality") or {}
    label = air.get("label") or {
        "GOOD": "좋음", "NORMAL": "보통", "BAD": "나쁨", "VERY_BAD": "매우 나쁨",
    }.get(air.get("grade"))
    pm10 = _number(air.get("pm10"))
    pm25 = _number(air.get("pm25"))
    if not (label or pm10 is not None or pm25 is not None):
        return ""
    numbers = []
    if pm10 is not None:
        numbers.append(f"PM10 {pm10:g}㎍/㎥")
    if pm25 is not None:
        numbers.append(f"PM2.5 {pm25:g}㎍/㎥")
    measurement = f" ({', '.join(numbers)})" if numbers else ""
    reading = f"{label} 수준" if label else "확인이 필요한 수준"
    advice = " 마스크를 챙겨보세요." if _air_is_bad(weather) else ""
    return f"미세먼지는 {reading}{measurement}이에요.{advice}"


def _weather_impact(code: str, weather: dict | None) -> str:
    """카드 본문에 들어갈 날씨 한 문장. 날씨가 없으면 빈 문자열."""
    if not weather:
        return ""
    rain_start = _rain_start(weather)
    humidity = _number(weather.get("humidity"))
    feels_like = _number(weather.get("feelsLike"))
    if code == "HEALTH":
        if rain_start or weather.get("condition") in WET_CONDITIONS:
            message = "비와 습도가 겹치면 실제보다 몸이 무겁게 느껴질 수 있어요."
        elif humidity is not None and humidity >= 80:
            message = "습도가 높아 더 나른하게 느껴질 수 있어요."
        elif feels_like is not None:
            message = f"체감온도는 {feels_like:g}℃예요."
        else:
            message = ""
        return " ".join(part for part in (message, _air_message(weather)) if part)
    if not rain_start:
        return ""
    return {
        "WORK": f"{rain_start}부터 비 소식이 있으니 바깥 일정은 그 전에 끝내두세요.",
        "LOVE": f"{rain_start}부터 비 소식이 있어 약속은 이동이 짧은 실내가 편해요.",
        "MONEY": "비 오는 시간에는 택시·배달처럼 편의를 위한 지출이 늘기 쉬워요.",
    }[code]


def _element_intro(analysis: dict) -> str:
    today_element = analysis["today_pillars"][2]["stem_element"]
    element_name = ELEMENT_NAMES[today_element]
    natal_count = analysis["element_counts"].get(today_element, 0)
    if natal_count <= 1:
        return f"사주에 부족했던 {element_name}의 기운이 오늘 들어오면서"
    if natal_count == 2:
        return f"사주에 자리한 {element_name}의 기운이 오늘 더해지면서"
    return f"오늘 {element_name}의 기운이 한층 강해지면서"


def _relationship_signal(analysis: dict) -> str:
    combinations, clashes = analysis["combinations"], analysis["clashes"]
    if combinations == clashes == 0:
        return "크게 부딪히는 합충이 없어 관계 흐름은 잔잔한 편이에요."
    if combinations > clashes:
        if combinations == 1:
            return "사람을 이어주는 합 기운이 하나 들어와 먼저 다가가면 분위기가 부드러워질 수 있어요."
        return "사람을 이어주는 합 기운이 도드라져 먼저 다가갈수록 분위기가 부드러워져요."
    if clashes > combinations:
        if clashes == 1:
            return "작은 부딪힘을 만드는 충 기운이 하나 보여 말의 속도를 조금 늦추는 게 좋아요."
        return "부딪힘을 만드는 충 기운이 도드라져 말의 속도를 조금 늦추는 게 좋아요."
    return "합과 충이 함께 들어와 가까워지는 흐름과 작은 마찰 가능성이 같이 있어요."


def build_campus_fortunes(*, analysis: dict, weather: dict | None, seed: str = "") -> list[dict]:
    """결과 화면 '상세 풀이'의 업무·연애·금전·건강 카드 4개를 만든다."""
    template_values = {
        "day_effect": TEN_GOD_EFFECTS[analysis["daily_ten_gods"]["day"]],
        "money_flow": MONEY_FLOW_MESSAGES[analysis["daily_ten_gods"]["month"]],
        "relationship_signal": _relationship_signal(analysis),
        "element_intro": _element_intro(analysis),
        "energy_flow": ENERGY_FLOW_MESSAGES[analysis["day_element_relation"]["code"]],
    }

    categories = []
    for code, definition in CATEGORY_DEFINITIONS.items():
        score = _category_score(code, analysis, weather)
        dots = score_to_dots(score)
        direction = CATEGORY_DIRECTIONS[code][0 if score >= 74 else 1]
        reason = CATEGORY_REASON_TEMPLATES[code].format(direction=direction, **template_values)
        action_prefix = {
            "MONEY": "점심 전에는",
            "HEALTH": "오후에 나른해지면",
        }.get(code, f"{_best_time(code, analysis, weather)}에는")
        categories.append({
            "code": code,
            "label": definition["label"],
            "headline": _headline(code, dots, seed),
            "score": dots,
            "interpretation": " ".join(part for part in (
                reason.strip(),
                _weather_impact(code, weather),
                f"{action_prefix} {CATEGORY_ACTIONS[code]}",
            ) if part),
        })
    return categories


def build_daily_message(*, level: LuckLevel, weather: dict | None, lucky_color: str) -> dict:
    """결과 화면 하단 '오늘의 한 줄' (제목 + 행운 컬러를 담은 제안 한 문장)."""
    wet = _rain_expected(weather)
    return {
        "title": DAILY_TITLES[level]["WET" if wet else "DRY"],
        "body": DAILY_BODIES[level].format(color=lucky_color),
    }


def has_current_categories(category_fortunes) -> bool:
    """저장된 카테고리가 현재 4개 카드 형식인지 확인한다."""
    if not category_fortunes:
        return False
    return (
        tuple(item.get("code") for item in category_fortunes) == CATEGORY_CODES
        and all("score" in item and "headline" in item for item in category_fortunes)
    )
