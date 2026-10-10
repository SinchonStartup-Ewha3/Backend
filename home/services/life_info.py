from dataclasses import dataclass

from django.db import models

RAINY_CONDITIONS = {"RAIN", "SHOWER", "SLEET"}
UMBRELLA_POP = 60          # 강수확률 60% 이상이면 우산
UMBRELLA_LOOKAHEAD = 12    # 앞으로 12시간 안의 비를 본다
BIG_TEMP_GAP = 10          # 일교차 10도 이상
STRONG_WIND = 9            # m/s


class CharacterState(models.TextChoices):
    DEFAULT = "DEFAULT", "기본"
    RAINY = "RAINY", "비"
    SNOWY = "SNOWY", "눈"
    COLD = "COLD", "추위"
    HOT = "HOT", "더위"


# (기준 기온 이상, 코드, 이름) — 위에서부터 처음 맞는 것
OUTFIT_TABLE = [
    (28, "SLEEVELESS", "민소매·반팔"),
    (23, "SHORT_SLEEVE", "반팔·얇은 셔츠"),
    (20, "LIGHT_LAYER", "얇은 가디건·긴팔"),
    (17, "KNIT", "니트·맨투맨"),
    (12, "CARDIGAN", "가디건·자켓"),
    (9, "TRENCH", "트렌치코트"),
    (5, "COAT", "코트"),
    (-100, "PADDED", "패딩"),
]


@dataclass
class LifeInfo:
    umbrella_needed: bool
    rain_from_hour: int | None
    outfit_code: str
    outfit_label: str
    temp_gap: float | None
    character: CharacterState
    message: str

    def to_dict(self) -> dict:
        return {
            "character": {"state": self.character.value, "label": self.character.label},
            "message": self.message,
            "lifeInfo": {
                "umbrella": {"needed": self.umbrella_needed, "fromHour": self.rain_from_hour},
                "outfit": {"code": self.outfit_code, "label": self.outfit_label},
                "tempGap": self.temp_gap,
            },
        }


def _first_rain_hour(hourly: list[dict]) -> int | None:
    for item in hourly[:UMBRELLA_LOOKAHEAD]:
        pop = item.get("precipitationProbability") or 0
        if item["condition"] in RAINY_CONDITIONS or pop >= UMBRELLA_POP:
            return item["hour"]
    return None


def _outfit(temp: float) -> tuple[str, str]:
    for threshold, code, label in OUTFIT_TABLE:
        if temp >= threshold:
            return code, label
    return OUTFIT_TABLE[-1][1:]


def _character(current: dict, raining_now: bool, feels: float) -> CharacterState:
    # 눈 > 비 > 추위 > 더위 > 기본
    if current["condition"] == "SNOW":
        return CharacterState.SNOWY
    if raining_now:
        return CharacterState.RAINY
    if feels <= 5:
        return CharacterState.COLD
    if feels >= 28:
        return CharacterState.HOT
    return CharacterState.DEFAULT


def _message(current, feels, raining_now, rain_hour, temp_gap) -> str:
    # 위에서부터 먼저 걸리는 문장 하나만 보여준다
    if current["condition"] == "SNOW":
        return "눈이 내려요. 미끄러운 길 조심하세요!"
    if raining_now:
        return "지금 비가 와요. 우산 꼭 챙기세요!"
    if rain_hour is not None:
        return f"{rain_hour}시쯤 비 소식이 있어요. 우산을 챙겨 나가세요!"
    if feels <= 0:
        return "많이 추워요. 두툼하게 껴입으세요!"
    if temp_gap is not None and temp_gap >= BIG_TEMP_GAP:
        return f"일교차가 {round(temp_gap)}도나 돼요. 겉옷을 챙기세요!"
    if feels <= 10:
        return "날씨가 제법 쌀쌀하니 감기에 조심하세요!"
    if feels >= 30:
        return "무더운 날이에요. 물을 자주 마셔주세요!"
    if (current.get("windSpeed") or 0) >= STRONG_WIND:
        return "바람이 강하게 불어요. 외출할 때 조심하세요!"
    if current.get("isNight"):
        return "포근한 밤이에요. 편안한 밤 보내세요!"
    return "산책하기 좋은 날씨예요!"


def build_life_info(current: dict, hourly: list[dict]) -> LifeInfo:
    """현재 날씨(get_current_weather)와 시간대별 날씨(get_hourly_weather)로 생활정보를 만든다"""
    temp = current.get("temperature")
    feels = current.get("feelsLike")
    feels = feels if feels is not None else (temp or 15.0)

    raining_now = current["condition"] in RAINY_CONDITIONS or (current.get("precipitation") or 0) > 0
    rain_hour = None if raining_now else get_first_rain_hour(hourly)

    min_t, max_t = current.get("minTemperature"), current.get("maxTemperature")
    temp_gap = round(max_t - min_t, 1) if min_t is not None and max_t is not None else None

    outfit_code, outfit_label = get_outfit(feels)

    return LifeInfo(
        umbrella_needed=raining_now or rain_hour is not None,
        rain_from_hour=rain_hour,
        outfit_code=outfit_code,
        outfit_label=outfit_label,
        temp_gap=temp_gap,
        character=_character(current, raining_now, feels),
        message=_message(current, feels, raining_now, rain_hour, temp_gap),
    )

def get_first_rain_hour(hourly: list[dict]) -> int | None:
    """앞으로 12시간 안에 처음 비가 예보된 시각(시). 없으면 None"""
    for item in hourly[:UMBRELLA_LOOKAHEAD]:
        pop = item.get("precipitationProbability") or 0
        if item["condition"] in RAINY_CONDITIONS or pop >= UMBRELLA_POP:
            return item["hour"]
    return None


def get_outfit(feels_like: float) -> tuple[str, str]:
    """체감온도에 맞는 옷차림 (코드, 이름)"""
    for threshold, code, label in OUTFIT_TABLE:
        if feels_like >= threshold:
            return code, label
    return OUTFIT_TABLE[-1][1:]