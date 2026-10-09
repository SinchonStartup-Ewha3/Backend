from datetime import date

from .scoring import best_block, day_word, nearest_day_items

RAIN_CONDITIONS = {"RAIN", "SHOWER", "SLEET", "SNOW"}
RUN_START, RUN_END = 6, 22
TIME_RANGES = (           # (시작, 끝, 동점일 때 선호 시각)
    (6, 12, 9),           # 아침
    (16, 22, 19),         # 저녁
)
BLOCK_HOURS = 3
GOOD_HOUR_SCORE = 70
IDEAL_FEELS = (10, 20)    # 러닝하기 좋은 체감온도
AIR_PENALTY = {"GOOD": 0, "NORMAL": 0, "BAD": 25, "VERY_BAD": 50}


def _feels(item: dict) -> float | None:
    feels = item.get("feelsLike")
    return feels if feels is not None else item.get("temperature")


def hour_score(item: dict, air_grade: str | None = None) -> int:
    if item["condition"] in RAIN_CONDITIONS:
        return 0
    score = 100.0
    score -= (item.get("precipitationProbability") or 0) * 0.5

    feels = _feels(item)
    if feels is not None:
        low, high = IDEAL_FEELS
        if feels < low:
            score -= (low - feels) * 4
        elif feels > high:
            score -= (feels - high) * 5

    humidity = item.get("humidity")
    if humidity is not None:
        if humidity > 70:
            score -= humidity - 70
        elif humidity < 30:
            score -= (30 - humidity) * 0.5

    wind = item.get("windSpeed")
    if wind is not None and wind >= 7:
        score -= 15

    score -= AIR_PENALTY.get(air_grade, 0)
    return max(0, min(100, round(score)))


def build_running_info(hourly: list[dict], today: date, air: dict | None = None,
                       uv: dict | None = None) -> dict:
    target, items = nearest_day_items(hourly, RUN_START, RUN_END)
    if not items:
        return {"targetDate": None, "score": None, "summary": "러닝 정보를 계산할 예보가 없어요.",
                "recommendedTimes": [], "uvIndex": uv, "overview": None}

    air_grade = air["grade"] if air else None
    scored = [{**item, "score": hour_score(item, air_grade)} for item in items]

    blocks = []
    for start, end, center in TIME_RANGES:
        part = [i for i in scored if start <= i["hour"] < end]
        block = best_block(part, BLOCK_HOURS, GOOD_HOUR_SCORE, center_hour=center)
        if block:
            blocks.append(block)

    # 대표 시각: 첫 추천 구간의 시작, 없으면 가장 점수 높은 시각
    if blocks:
        block_hours = {
            int(b["start"][:2]) + k for b in blocks for k in range(BLOCK_HOURS)
        }
        score = round(sum(i["score"] for i in scored if i["hour"] in block_hours) / len(block_hours))
        first_hour = int(blocks[0]["start"][:2])
        rep = next(i for i in scored if i["hour"] == first_hour)
    else:
        rep = max(scored, key=lambda i: i["score"])
        score = rep["score"]

    day = day_word(target, today)
    feels = _feels(rep)
    any_rain = any(i["condition"] in RAIN_CONDITIONS for i in items)
    humid = (rep.get("humidity") or 0) > 70

    if blocks and score >= 80 and not humid:
        summary = f"{day}은 비가 오지 않고 체감온도와 습도 모두 적당해 러닝하기에 최적의 날씨예요."
    elif blocks and humid:
        summary = f"{day}은 비 소식은 없지만 습도가 조금 높아요. 추천 시간대에 수분을 챙기며 달려보세요."
    elif blocks:
        summary = f"{day}은 추천 시간대에 맞춰 가볍게 달려보세요."
    elif blocks:
        summary = f"{day}은 추천 시간대에 맞춰 가볍게 달려보세요."
    elif air_grade in ("BAD", "VERY_BAD"):
        summary = f"{day}은 미세먼지가 나빠 야외 러닝보다 실내 운동을 추천해요."
    elif any_rain:
        summary = f"{day}은 비 소식이 있어 실내 러닝을 추천해요."
    elif feels is not None and feels > IDEAL_FEELS[1] + 6:
        summary = f"{day}은 더워서 야외 러닝이 무리가 될 수 있어요. 실내 운동을 추천해요."
    elif feels is not None and feels < IDEAL_FEELS[0] - 7:
        summary = f"{day}은 많이 추워요. 충분히 몸을 풀고 짧게 달리거나 실내 운동을 추천해요."
    else:
        summary = f"{day}은 러닝하기 좋은 시간대가 없어요. 실내 운동을 추천해요."

    return {
        "targetDate": target,
        "score": score,
        "summary": summary,
        "recommendedTimes": blocks,
        "uvIndex": uv,
        "overview": {
            "precipitationProbability": max(i.get("precipitationProbability") or 0 for i in items),
            "humidity": rep.get("humidity"),
            "feelsLike": feels,
            "airQuality": air,
        },
    }