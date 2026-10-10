from datetime import date, timedelta

from .scoring import best_block

RAIN_CONDITIONS = {"RAIN", "SHOWER", "SLEET", "SNOW"}
DAY_START, DAY_END = 9, 18      # 9시~17시 예보를 본다
GOOD_HOUR_SCORE = 70            # 추천 시간대 기준
RAIN_DAY_MAX_SCORE = 30         # 낮에 비 예보가 있으면 최대 점수
HUMIDITY_OK = 40                # 이 습도까지는 감점 없음
RECOMMEND_HOURS = 3 

def wind_label(speed: float | None) -> str | None:
    if speed is None:
        return None
    if speed < 2:
        return "약함"
    if speed < 5:
        return "보통"
    return "강함"


def hour_score(item: dict) -> int:
    """한 시간의 빨래 건조 점수 (0~100)"""
    if item["condition"] in RAIN_CONDITIONS:
        return 0
    score = 100.0
    score -= (item.get("precipitationProbability") or 0) * 0.6
    humidity = item.get("humidity")
    if humidity is not None and humidity > HUMIDITY_OK:
        score -= (humidity - HUMIDITY_OK) * 0.8
    score -= {"PARTLY_CLOUDY": 5, "CLOUDY": 15}.get(item["condition"], 0)
    wind = item.get("windSpeed")
    if wind is not None:
        if wind < 1:
            score -= 5          # 바람이 거의 없으면 잘 안 마름
        elif wind >= 9:
            score -= 15         # 너무 강하면 빨래가 날아감
    return max(0, min(100, round(score)))


def _daytime_items(hourly: list[dict]) -> tuple[str | None, list[dict]]:
    """가장 가까운 날의 낮 시간 예보만 고른다 (저녁이면 내일)"""
    target, result = None, []
    for item in hourly:
        if not DAY_START <= item["hour"] < DAY_END:
            continue
        item_date = item["time"][:10]
        if target is None:
            target = item_date
        if item_date != target:
            break
        result.append(item)
    return target, result


def _average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _day_word(target: str, today: date) -> str:
    if target == today.isoformat():
        return "오늘"
    if target == (today + timedelta(days=1)).isoformat():
        return "내일"
    month, day = int(target[5:7]), int(target[8:10])
    return f"{month}월 {day}일"


def build_laundry_info(hourly: list[dict], today: date) -> dict:
    target, items = _daytime_items(hourly)
    if not items:
        return {"targetDate": None, "score": None, "summary": "빨래 정보를 계산할 예보가 없어요.",
                "overview": None, "recommendedTime": None, "recommendedMessage": None}

    scored = [{**item, "score": hour_score(item)} for item in items]
    any_rain = any(item["condition"] in RAIN_CONDITIONS for item in items)

    score = round(_average([i["score"] for i in scored]))
    if any_rain:
        score = min(score, RAIN_DAY_MAX_SCORE)

    pop = max(item.get("precipitationProbability") or 0 for item in items)
    humidity = _average([i["humidity"] for i in items if i.get("humidity") is not None])
    wind = _average([i["windSpeed"] for i in items if i.get("windSpeed") is not None])
    humidity = round(humidity) if humidity is not None else None
    wind = round(wind, 1) if wind is not None else None

    day = _day_word(target, today)
    parts = [f"강수 {pop:.0f}%"]
    if humidity is not None:
        parts.append(f"습도 {humidity}%")
    if wind is not None:
        parts.append(f"풍속 {wind_label(wind)}")
    summary = f"{day}은 {', '.join(parts)}으로 예상돼요. "

    if any_rain or pop >= 60:
        summary += "비 소식이 있어 실외 건조는 피하고 실내에서 말리는 걸 추천해요."
    elif score >= 80:
        summary += "비가 오지 않고 습도도 높지 않아 빨래하기 좋은 날씨예요."
    elif score >= 60:
        summary += "빨래하기 무난하지만 건조에 시간이 조금 걸릴 수 있어요."
    else:
        summary += "습도가 높아 실외 건조가 어려워요. 제습기나 선풍기를 함께 써보세요."

    window = best_block(scored, RECOMMEND_HOURS, GOOD_HOUR_SCORE)
    if window:
        recommended_message = (
            f"{window['start']} - {window['end']} 사이가 습도가 낮고 비 소식이 없어 가장 잘 마를 거예요."
        )
    else:
        recommended_message = f"{day}은 밖에서 빨래가 잘 마를 시간대가 없어요. 실내 건조를 추천해요."

    return {
        "targetDate": target,
        "score": score,
        "summary": summary,
        "overview": {
            "precipitationProbability": pop,
            "humidity": humidity,
            "windSpeed": wind,
            "windLabel": wind_label(wind),
        },
        "recommendedTime": window,
        "recommendedMessage": recommended_message,
    }