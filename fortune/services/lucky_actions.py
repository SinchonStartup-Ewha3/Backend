"""날씨별 '오늘의 행운 행동' 문구와 오늘 날씨 분류."""
import hashlib

# 날씨 분류 → 행운 행동 후보
LUCKY_ACTIONS = {
    "CLEAR": [
        "오늘은 하늘이 맑으니, 잠깐이라도 밖에 나가 햇빛을 쐬어보는 거예요.",
        "맑은 날엔 괜히 창문을 활짝 열어보는 것, 그게 오늘의 행운 행동이에요.",
        "하늘이 좋은 날엔 평소 안 가던 길로 한 번 돌아가 보세요.",
        "오늘처럼 맑은 날엔, 좋아하는 노래를 크게 틀고 걸어보는 거예요.",
        "맑은 하늘 아래서 사진 한 장 남겨보는 건 어떨까요.",
        "날이 좋으니, 점심은 밖에서 먹어보는 것도 좋은 선택이에요.",
    ],
    "CLOUDY": [
        "오늘은 하늘이 우중충하니, 비타민 D를 챙겨 먹는 게 오늘의 행운 행동이에요.",
        "흐린 날엔 좋아하는 향의 차 한 잔이 기분을 살려줄 거예요.",
        "하늘이 잔뜩 흐린 날엔, 평소보다 조명을 하나 더 켜보세요.",
        "우중충한 날씨엔 밝은 색 옷을 골라 입어보는 거, 은근히 효과 있어요.",
        "흐린 하늘 아래서는 좋아하는 플레이리스트로 기분을 채워보세요.",
        "오늘 같은 날엔, 창밖 대신 좋아하는 사람 얼굴을 한 번 더 보는 거예요.",
    ],
    "RAIN": [
        "비 오는 날엔 웅덩이를 한 번 밟아보는 거, 은근히 기분 좋아져요.",
        "오늘은 우산 속에서 빗소리에 잠깐 귀 기울여보세요.",
        "비 오는 날엔 따뜻한 국물 요리가 오늘의 행운 메뉴예요.",
        "창문 너머로 떨어지는 빗방울을 잠깐 멍하니 바라봐 보세요.",
        "비 오는 날 우산 색깔을 평소보다 화사한 걸로 골라보는 거예요.",
        "오늘은 실내에서 좋아하는 영화 한 편, 딱 좋은 타이밍이에요.",
        "빗소리를 들으며 잠깐 눈을 감고 쉬어가는 것도 행운이에요.",
        "비 오는 날엔 평소보다 천천히 걸어보는 거, 마음이 편해져요.",
    ],
    "SNOW": [
        "눈 오는 날엔 발자국을 하나 남기고 뒤돌아보는 거예요.",
        "첫눈처럼 소복이 쌓인 곳을 살짝 밟아보는 것도 행운이에요.",
        "눈 오는 날엔 따뜻한 코코아 한 잔이 오늘의 행운템이에요.",
        "눈송이가 떨어지는 걸 잠깐 하늘 보며 세어보세요.",
        "눈 쌓인 풍경 사진 한 장, 오늘의 기록으로 남겨보는 거예요.",
        "눈 오는 날엔 목도리를 한 번 더 여며보는 것도 좋아요.",
    ],
    "WINDY": [
        "바람이 센 날엔 모자보다 머리끈을 챙기는 게 오늘의 지혜예요.",
        "강풍 부는 날엔 옷깃을 단단히 여미고, 마음도 단단히 먹어보세요.",
        "바람이 많이 부는 날엔 창문 단속 한 번 더 확인해보는 거예요.",
        "오늘처럼 바람 센 날엔, 실내에서 할 일을 먼저 끝내보는 게 좋아요.",
    ],
    "HOT": [
        "무더운 날엔 시원한 수박 한 조각이 오늘의 행운템이에요.",
        "폭염엔 그늘 따라 걷는 것도 은근히 행운을 부르는 방법이에요.",
        "오늘처럼 더운 날엔 물을 평소보다 한 잔 더 마셔보세요.",
        "더위 심한 날엔 잠깐이라도 에어컨 바람 아래서 숨 돌려보는 거예요.",
        "무더운 날엔 아이스크림 하나쯤은 오늘의 작은 행운이에요.",
    ],
    "COLD": [
        "추운 날엔 핫팩 하나 주머니에 챙겨보는 게 오늘의 지혜예요.",
        "한파엔 목도리를 두 번 감아보는 것도 오늘의 행운 행동이에요.",
        "추운 날씨엔 따뜻한 차 한 잔이 오늘의 행운 아이템이에요.",
        "오늘처럼 추운 날엔, 가장 두꺼운 양말을 꺼내 신어보세요.",
        "한파주의보인 날엔 실내에서 몸 녹이는 시간을 꼭 가져보세요.",
    ],
    "TEMP_GAP": [
        "일교차 큰 날엔 얇은 겉옷 하나 가방에 챙겨두는 게 행운이에요.",
        "오늘처럼 아침저녁 기온 차가 큰 날엔, 목을 따뜻하게 감싸보세요.",
        "일교차 심한 날엔 따뜻한 물 한 잔으로 하루를 시작해보는 거예요.",
    ],
}

CATEGORY_LABELS = {
    "CLEAR": "맑음",
    "CLOUDY": "흐림",
    "RAIN": "비",
    "SNOW": "눈",
    "WINDY": "강풍",
    "HOT": "폭염",
    "COLD": "한파",
    "TEMP_GAP": "큰 일교차",
}

RAIN_CONDITIONS = {"RAIN", "SHOWER", "SLEET"}
HOT_FEELS = 33       # 체감온도 33도 이상: 폭염
COLD_FEELS = -5      # 체감온도 -5도 이하: 한파
STRONG_WIND = 9      # m/s
BIG_TEMP_GAP = 10    # 일교차 10도 이상


def weather_category(weather: dict | None) -> str | None:
    """오늘 날씨를 행운 행동 분류로 바꾼다. 날씨를 모르면 None."""
    if not weather or not weather.get("condition"):
        return None
    condition = weather["condition"]
    if condition == "SNOW":
        return "SNOW"
    if condition in RAIN_CONDITIONS:
        return "RAIN"

    feels = weather.get("feelsLike")
    if feels is not None and feels >= HOT_FEELS:
        return "HOT"
    if feels is not None and feels <= COLD_FEELS:
        return "COLD"
    if (weather.get("windSpeed") or 0) >= STRONG_WIND:
        return "WINDY"
    low, high = weather.get("minTemperature"), weather.get("maxTemperature")
    if low is not None and high is not None and high - low >= BIG_TEMP_GAP:
        return "TEMP_GAP"
    if condition in {"CLOUDY", "PARTLY_CLOUDY"}:
        return "CLOUDY"
    return "CLEAR"


def pick_lucky_action(category: str | None, seed: str) -> str | None:
    """같은 사람·같은 날짜면 항상 같은 행운 행동을 고른다."""
    if category is None:
        return None
    options = LUCKY_ACTIONS[category]
    digest = hashlib.sha256(f"{seed}:lucky-action".encode()).hexdigest()
    return options[int(digest, 16) % len(options)]