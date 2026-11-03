"""사주 신호와 실제 날씨를 대학생활 6개 카테고리로 번역한다."""
from datetime import datetime, time

from .saju import TEN_GOD_LABELS, hour_pillar, ten_god


CATEGORY_DEFINITIONS = {
    "ACADEMIC": {
        "label": "학업운",
        "subtitle": "공부 방식과 집중 시간",
        "weights": {
            "DIRECT_RESOURCE": 12, "INDIRECT_RESOURCE": 9,
            "EATING_GOD": 7, "DIRECT_OFFICER": 5,
            "HURTING_OFFICER": -2, "ROBBER": -3,
        },
    },
    "LOVE": {
        "label": "연애운",
        "subtitle": "연락·약속·감정 해석",
        "weights": {
            "DIRECT_WEALTH": 9, "INDIRECT_WEALTH": 8,
            "DIRECT_OFFICER": 9, "SEVEN_KILLINGS": 6,
            "EATING_GOD": 6, "HURTING_OFFICER": 4,
        },
    },
    "RELATIONSHIPS": {
        "label": "인간관계운",
        "subtitle": "귀인과 캠퍼스 관계",
        "weights": {
            "FRIEND": 11, "DIRECT_RESOURCE": 8, "INDIRECT_RESOURCE": 6,
            "EATING_GOD": 6, "ROBBER": 2, "SEVEN_KILLINGS": -4,
        },
    },
    "MONEY": {
        "label": "재물운",
        "subtitle": "실제 소비 유혹",
        "weights": {
            "DIRECT_WEALTH": 13, "INDIRECT_WEALTH": 10,
            "EATING_GOD": 6, "DIRECT_OFFICER": 3,
            "ROBBER": -11, "HURTING_OFFICER": -3,
        },
    },
    "WEATHER": {
        "label": "날씨운",
        "subtitle": "오행 에너지와 오늘 날씨",
        "weights": {
            "FRIEND": 9, "EATING_GOD": 7, "DIRECT_RESOURCE": 6,
            "INDIRECT_RESOURCE": 4, "SEVEN_KILLINGS": -7,
            "HURTING_OFFICER": -2,
        },
    },
    "COMMUTE": {
        "label": "통학운",
        "subtitle": "강수 시각과 등하교 전략",
        "weights": {
            "DIRECT_OFFICER": 7, "DIRECT_WEALTH": 6, "FRIEND": 5,
            "EATING_GOD": 4, "SEVEN_KILLINGS": -4, "ROBBER": -2,
        },
    },
}

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
    "ROBBER": "오늘은 겁재 기운이 들어와 친구들과 어울리는 자리에서 예상 밖의 지출이 늘기 쉬워요.",
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
    "ACADEMIC": ("가장 어려운 과목을 25분만 먼저 시작해보세요.", "밤에는 새로운 과제를 한꺼번에 벌이지 않는 게 좋아요."),
    "LOVE": ("안부와 함께 답하기 쉬운 질문 하나를 보내보세요.", "답장 속도만으로 상대의 마음을 단정하지 마세요."),
    "RELATIONSHIPS": ("필요한 도움을 한 가지로 좁혀 구체적으로 요청해보세요.", "단체 채팅에서는 감정적으로 바로 답하지 않는 게 좋아요."),
    "MONEY": ("오늘 사용할 금액의 상한을 먼저 정해두세요.", "피곤할 때 배달·택시·쇼핑을 연달아 결제하지 마세요."),
    "WEATHER": ("물을 마시고 10분 정도 가볍게 걸어보세요.", "카페인만으로 피로를 계속 미루지 않는 게 좋아요."),
    "COMMUTE": ("비 오는 시간과 마지막 이동 경로를 확인해보세요.", "예보를 보지 않고 우산 없이 이동하지 마세요."),
}

CATEGORY_REASON_TEMPLATES = {
    "ACADEMIC": "오늘은 {day_effect}이 들어와 해야 할 일에 집중하기 좋은 날이에요. {direction}",
    "LOVE": "{relationship_signal} 감정을 서두르기보다 상대의 마음을 차분히 살펴보면 좋아요. {direction}",
    "RELATIONSHIPS": "오늘은 귀인과 대인관계의 흐름이 비교적 차분한 날이에요. {relationship_signal} {direction}",
    "MONEY": "{money_flow} {direction}",
    "WEATHER": "{element_intro}, {energy_flow} 실제 날씨까지 함께 보면 {direction}",
    "COMMUTE": "오늘은 마음이 조금 급해질 수 있는 흐름이에요. 시간대별 기운을 실제 비와 바람 예보에 함께 맞춰보면 {direction}",
}

CATEGORY_DIRECTIONS = {
    "ACADEMIC": (
        "어려운 과목이나 중요한 과제를 먼저 잡아도 좋아요.",
        "공부 범위를 줄이고 한 단원씩 끝내는 편이 좋아요.",
    ),
    "LOVE": (
        "가볍게 먼저 연락하며 분위기를 열어도 좋아요.",
        "상대의 반응을 빠르게 단정하지 않는 편이 좋아요.",
    ),
    "RELATIONSHIPS": (
        "필요한 도움을 구체적으로 요청하면 답을 얻기 좋아요.",
        "감정적인 반응보다 사실을 확인하는 편이 좋아요.",
    ),
    "MONEY": (
        "계획한 소비는 괜찮지만 결제 전에 목적을 한 번 확인해보세요.",
        "편의를 위한 작은 결제가 겹치지 않도록 한도를 정해두는 게 좋아요.",
    ),
    "WEATHER": (
        "중요한 일정을 컨디션이 좋은 시간에 먼저 배치해도 좋아요.",
        "집중 시간을 짧게 나누고 쉬는 시간을 챙기는 편이 좋아요.",
    ),
    "COMMUTE": (
        "예보에 맞춰 출발 시간을 조정하면 이동 변수를 줄일 수 있어요.",
        "환승과 도보 시간을 평소보다 여유 있게 잡는 편이 좋아요.",
    ),
}

ENERGY_FLOW_MESSAGES = {
    "SUPPORTED": "나를 도와주는 흐름이라 에너지가 자연스럽게 채워지는 날이에요.",
    "SAME": "나와 비슷한 기운이 겹쳐 평소의 장점과 추진력이 또렷해지는 날이에요.",
    "OUTPUT": "내 기운이 바깥으로 많이 흐르는 날이라 활동한 만큼 쉽게 지칠 수 있어요.",
    "CONTROLS": "주변 흐름을 직접 정리해야 해서 생각보다 에너지를 많이 쓰게 될 수 있어요.",
    "CONTROLLED": "부족한 부분은 보완되지만 오늘의 기운이 나를 조금 누르는 흐름도 있어, 서두르면 평소보다 쉽게 지칠 수 있어요.",
}


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


def _weather_modifiers(weather: dict | None) -> dict[str, int]:
    result = {code: 0 for code in CATEGORY_DEFINITIONS}
    if not weather:
        return result

    humidity = _number(weather.get("humidity"))
    feels_like = _number(weather.get("feelsLike"))
    wind = _number(weather.get("windSpeed"))
    minimum = _number(weather.get("minTemperature"))
    maximum = _number(weather.get("maxTemperature"))
    rain_expected = weather.get("condition") in WET_CONDITIONS or any(
        _is_wet(item) for item in _hourly(weather)
    )

    if humidity is not None and humidity >= 80:
        result["ACADEMIC"] -= 3
        result["WEATHER"] -= 4
    if feels_like is not None and (feels_like <= 0 or feels_like >= 30):
        result["WEATHER"] -= 6
        result["COMMUTE"] -= 4
    if wind is not None and wind >= 7:
        result["COMMUTE"] -= 6
    if minimum is not None and maximum is not None and maximum - minimum >= 10:
        result["WEATHER"] -= 3
        result["COMMUTE"] -= 3
    if rain_expected:
        result["MONEY"] -= 4
        result["COMMUTE"] -= 9

    air = weather.get("airQuality") or {}
    if (
        air.get("grade") in {"BAD", "VERY_BAD"}
        or (_number(air.get("pm10")) or 0) > 80
        or (_number(air.get("pm25")) or 0) > 35
    ):
        result["WEATHER"] -= 4
        result["COMMUTE"] -= 4
    return result


def _category_score(code: str, analysis: dict, weather: dict | None) -> int:
    definition = CATEGORY_DEFINITIONS[code]
    score = 68.0
    for period, god in analysis["daily_ten_gods"].items():
        score += definition["weights"].get(god, 0) * PERIOD_WEIGHT[period]
    score += min(analysis["combinations"], 2) * (5 if code in {"LOVE", "RELATIONSHIPS"} else 2)
    score -= min(analysis["clashes"], 2) * (6 if code in {"LOVE", "RELATIONSHIPS"} else 3)
    score += _weather_modifiers(weather)[code]
    return max(40, min(95, round(score)))


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


def _time_recommendations(code: str, analysis: dict, weather: dict | None) -> tuple[str, str]:
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
            value -= 5 if code in {"COMMUTE", "RELATIONSHIPS"} else 2
        humidity = _number(item.get("humidity"))
        if humidity is not None and humidity >= 85 and code in {"ACADEMIC", "WEATHER"}:
            value -= 3
        candidates.append((value, item))
    if not candidates:
        defaults = {
            "ACADEMIC": ("오전 10시~낮 12시", "오후 3시~5시"),
            "LOVE": ("오후 1시~3시", "밤 10시 이후"),
            "RELATIONSHIPS": ("수업 직후", "피곤한 저녁 시간"),
            "MONEY": ("점심 결제 전", "오후 9시 이후"),
            "WEATHER": ("오전 9시~11시", "오후 3시~5시"),
            "COMMUTE": ("출발 전 예보 확인 후", "강수 가능성이 높은 시간"),
        }
        return defaults[code]
    best = max(candidates, key=lambda row: row[0])[1]
    caution = min(candidates, key=lambda row: row[0])[1]
    return _format_hour(best), _format_hour(caution)


def _rain_start(weather: dict | None) -> str | None:
    return _format_hour(next((item for item in _hourly(weather) if _is_wet(item)), None))


def _weather_impact(code: str, weather: dict | None) -> str:
    if not weather:
        return "날씨 정보가 없어서 오늘은 사주 흐름을 중심으로 봤어요."
    rain_start = _rain_start(weather)
    humidity = _number(weather.get("humidity"))
    feels_like = _number(weather.get("feelsLike"))
    wind = _number(weather.get("windSpeed"))
    if rain_start:
        messages = {
            "ACADEMIC": f"{rain_start}부터 비 가능성이 있어 이후에는 밝고 조용한 실내 공부가 잘 맞아요.",
            "LOVE": f"{rain_start}부터 비 가능성이 있으니 약속은 이동이 짧은 실내 장소가 편해요.",
            "RELATIONSHIPS": f"{rain_start}까지 필요한 만남을 잡고, 이후에는 메시지로 가볍게 안부를 이어가보세요.",
            "MONEY": "비 오는 시간에는 택시·배달·편의점 우산처럼 편의를 위한 지출이 늘기 쉬워요.",
            "WEATHER": "비와 높은 습도가 겹치면 오후에 실제 기운보다 몸이 무겁게 느껴질 수 있어요.",
            "COMMUTE": f"{rain_start}부터 비 가능성이 있어 그 전에 주요 이동을 끝내는 편이 안전해요.",
        }
        weather_message = messages[code]
    elif code == "WEATHER" and humidity is not None and humidity >= 80:
        weather_message = "습도가 높아 실제 기운보다 더 나른하게 느껴질 수 있으니 짧게 자주 움직이는 편이 좋아요."
    elif code == "COMMUTE" and wind is not None and wind >= 7:
        weather_message = "바람이 강하니 도보나 자전거 이동 시간을 평소보다 여유 있게 잡는 편이 좋아요."
    elif code == "WEATHER" and feels_like is not None:
        weather_message = f"현재 체감온도는 {feels_like:g}℃예요. 겉옷과 쉬는 간격을 날씨에 맞춰 조절해보세요."
    else:
        weather_message = "큰 날씨 변수는 적어서 오늘의 좋은 흐름을 그대로 활용하기 좋아요."

    air = weather.get("airQuality") or {}
    grade = air.get("grade")
    label = air.get("label") or {
        "GOOD": "좋음", "NORMAL": "보통", "BAD": "나쁨", "VERY_BAD": "매우 나쁨",
    }.get(grade)
    pm10 = _number(air.get("pm10"))
    pm25 = _number(air.get("pm25"))
    air_is_bad = (
        grade in {"BAD", "VERY_BAD"}
        or (pm10 or 0) > 80
        or (pm25 or 0) > 35
    )
    if code == "WEATHER" and (label or pm10 is not None or pm25 is not None):
        reading = f"{label} 수준" if label else "확인이 필요한 수준"
        numbers = []
        if pm10 is not None:
            numbers.append(f"PM10 {pm10:g}㎍/㎥")
        if pm25 is not None:
            numbers.append(f"PM2.5 {pm25:g}㎍/㎥")
        measurement = f" ({', '.join(numbers)})" if numbers else ""
        advice = (
            " 오래 밖에 있기보다 마스크를 챙기고 실내에서 쉬는 시간을 확보해보세요."
            if air_is_bad else " 야외 일정도 현재 컨디션에 맞춰 조절해보세요."
        )
        weather_message += f" 오늘 미세먼지는 {reading}{measurement}이에요.{advice}"
    elif code == "COMMUTE" and air_is_bad:
        weather_message += " 미세먼지가 나쁜 편이니 통학할 때 마스크를 챙겨보세요."
    return weather_message


def _element_intro(analysis: dict) -> str:
    today_element = analysis["today_pillars"][2]["stem_element"]
    element_name = ELEMENT_NAMES[today_element]
    natal_count = analysis["element_counts"].get(today_element, 0)
    if natal_count <= 1:
        return f"사주에 부족했던 {element_name}의 기운이 오늘 들어오면서"
    if natal_count == 2:
        return f"사주에 자리한 {element_name}의 기운이 오늘 더해지면서"
    return f"오늘 {element_name}의 기운이 한층 강해지면서"


def build_campus_fortunes(*, analysis: dict, weather: dict | None) -> list[dict]:
    """일관된 계산 근거를 가진 유료 카테고리 6개를 만든다."""
    day_god = analysis["daily_ten_gods"]["day"]
    day_effect = TEN_GOD_EFFECTS[day_god]
    if analysis["combinations"] == analysis["clashes"] == 0:
        relationship_signal = "크게 부딪히는 합충이 없어 관계 흐름은 비교적 잔잔한 편이에요."
    elif analysis["combinations"] > analysis["clashes"]:
        if analysis["combinations"] == 1:
            relationship_signal = "사람을 이어주는 합 기운이 하나 들어와 먼저 다가가면 분위기가 부드러워질 수 있어요."
        else:
            relationship_signal = "사람을 이어주는 합 기운이 도드라져 먼저 다가갈수록 분위기가 부드러워져요."
    elif analysis["clashes"] > analysis["combinations"]:
        if analysis["clashes"] == 1:
            relationship_signal = "작은 부딪힘을 만드는 충 기운이 하나 보여 말과 반응의 속도를 조금 늦추는 게 좋아요."
        else:
            relationship_signal = "부딪힘을 만드는 충 기운이 도드라져 말과 반응의 속도를 조금 늦추는 게 좋아요."
    else:
        relationship_signal = "합과 충이 함께 들어와 가까워지는 흐름과 작은 마찰 가능성이 같이 있어요."

    energy_flow = ENERGY_FLOW_MESSAGES[analysis["day_element_relation"]["code"]]
    element_intro = _element_intro(analysis)

    categories = []
    for code, definition in CATEGORY_DEFINITIONS.items():
        score = _category_score(code, analysis, weather)
        best_time, _ = _time_recommendations(code, analysis, weather)
        action, avoid = CATEGORY_ACTIONS[code]
        score_direction = CATEGORY_DIRECTIONS[code][0 if score >= 74 else 1]
        month_god = analysis["daily_ten_god_labels"]["month"]
        money_flow = MONEY_FLOW_MESSAGES[analysis["daily_ten_gods"]["month"]]
        reason = CATEGORY_REASON_TEMPLATES[code].format(
            day_effect=day_effect,
            day_god=TEN_GOD_LABELS[day_god],
            month_god=month_god,
            money_flow=money_flow,
            relationship_signal=relationship_signal,
            element_intro=element_intro,
            energy_flow=energy_flow,
            direction=score_direction,
        )
        action_prefix = {
            "MONEY": "점심 전에는",
            "WEATHER": "오후에 나른해지면",
            "COMMUTE": "외출 전에는",
        }.get(code, f"{best_time}에는")
        categories.append({
            "code": code,
            "label": definition["label"],
            "interpretation": " ".join((
                reason,
                _weather_impact(code, weather),
                f"{action_prefix} {action}",
                avoid,
            )),
        })
    return categories
