from collections import Counter
from datetime import datetime, timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from home.services.life_info import build_life_info
from home.services.weather import (
    get_current_weather,
    get_hourly_weather,
)

from community.models import Post

from .liner_client import generate_community_copy


FIXED_SUB_MESSAGE = (
    "알림으로 미리 준비해요"
)

PREMIUM_TARGET_URL = "/premium"


def _district_prefix(region) -> str:
    """
    '서울특별시 서대문구 신촌동'에서
    '서울특별시 서대문구'를 반환합니다.
    """

    parts = region.region_name.split()

    if len(parts) >= 2:
        return " ".join(parts[:2])

    return region.region_name


def _recent_consistent_posts(region) -> list[dict]:
    """
    같은 시군구의 최근 게시글을 조회합니다.

    가장 많이 선택된 태그가 전체 게시글의 일정 비율 이상일 때만
    게시글을 AI 참고자료로 사용합니다.
    """

    since = timezone.now() - timedelta(
        hours=settings.COMMUNITY_COPY_RECENT_HOURS
    )

    district = _district_prefix(region)

    posts = list(
        Post.objects.filter(
            region__region_name__startswith=district,
            created_at__gte=since,
        )
        .order_by("-created_at")
        .values("content", "tag")[:20]
    )

    if len(posts) < settings.COMMUNITY_COPY_MIN_POSTS:
        return []

    tag_counts = Counter(
        post["tag"] for post in posts
    )

    top_tag, top_count = tag_counts.most_common(1)[0]

    consistency = top_count / len(posts)

    if consistency < settings.COMMUNITY_COPY_CONSISTENCY_RATIO:
        return []

    # 닉네임이나 사용자 ID는 전달하지 않습니다.
    return [
        {
            "content": post["content"],
            "tag": post["tag"],
        }
        for post in posts
        if post["tag"] == top_tag
    ][:5]


def _fallback_copy(
    current_weather: dict,
    hourly_weather: list[dict],
    *,
    time_scope: str = "TODAY",
) -> dict:
    """LINER 장애 시 사용할 규칙 기반 기본 문구입니다."""

    life_info = build_life_info(
        current_weather,
        hourly_weather,
    )

    feels_like = current_weather.get("feelsLike")
    if feels_like is None:
        feels_like = current_weather.get("temperature")
    if feels_like is None:
        feels_like = 15

    humidity = current_weather.get("humidity")
    condition = current_weather.get("condition")
    is_tomorrow = time_scope == "TOMORROW"

    if life_info.character.value == "SNOWY":
        headline_title = "내일은 눈이 내려요" if is_tomorrow else "눈이 내리는 오늘"
    elif life_info.umbrella_needed:
        headline_title = "내일은 비 소식이 있어요" if is_tomorrow else "비 소식이 있는 오늘"
    elif feels_like <= 5:
        headline_title = "내일은 기온이 뚝 떨어져요" if is_tomorrow else "기온이 뚝 떨어진 오늘"
    elif feels_like >= 28:
        headline_title = "내일은 기온이 크게 올라요" if is_tomorrow else "기온이 크게 오른 오늘"
    else:
        headline_title = "가볍게 외출하기 좋은 내일" if is_tomorrow else "가볍게 외출하기 좋은 오늘"

    if life_info.umbrella_needed:
        headline_description = (
            f"{life_info.outfit_label} 차림과 우산을 추천해요"
        )
        action_type = "UMBRELLA"
        premium_message = (
            "내일 외출 전 우산을 준비해두세요"
            if is_tomorrow
            else "외출 전 우산을 꼭 챙겨주세요"
        )

    elif feels_like <= 5:
        headline_description = (
            f"{life_info.outfit_label} 차림으로 따뜻하게 입어주세요"
        )
        action_type = "COLD"
        premium_message = "내일은 따뜻한 겉옷이 필요해요" if is_tomorrow else "오늘은 따뜻한 겉옷을 챙겨주세요"

    elif feels_like >= 28:
        headline_description = (
            f"{life_info.outfit_label}처럼 가볍게 입어주세요"
        )
        action_type = "HYDRATION"
        premium_message = "내일은 물을 가까이 두고 자주 마셔요" if is_tomorrow else "오늘은 물을 자주 마셔주세요"

    elif humidity is not None and humidity >= 75:
        headline_description = (
            f"{life_info.outfit_label} 차림을 추천해요"
        )
        action_type = "INDOOR_DRYING"
        premium_message = "내일 빨래는 실내 건조가 좋아요" if is_tomorrow else "오늘 빨래는 실내 건조를 추천해요"

    elif (
        humidity is not None
        and humidity <= 60
        and condition in {"CLEAR", "PARTLY_CLOUDY"}
    ):
        headline_description = (
            f"{life_info.outfit_label} 차림을 추천해요"
        )
        action_type = "LAUNDRY"
        premium_message = "내일은 빨래하기 좋은 날씨예요" if is_tomorrow else "오늘은 빨래하기 좋은 날씨예요"

    elif 10 <= feels_like <= 25:
        headline_description = (
            f"{life_info.outfit_label} 차림을 추천해요"
        )
        action_type = "EXERCISE"
        premium_message = "내일은 가볍게 움직이기 좋아요" if is_tomorrow else "오늘은 가벼운 야외 운동을 추천해요"

    else:
        headline_description = (
            "내일 날씨에 맞춰 미리 준비해보세요"
            if is_tomorrow
            else life_info.message
        )
        action_type = "WEATHER"
        premium_message = (
            "내일 날씨에 맞춰 하루를 준비해보세요"
            if is_tomorrow
            else "오늘의 날씨에 맞춰 하루를 준비해보세요"
        )

    return {
        "headlineTitle": headline_title,
        "headlineDescription": "",
        "premiumMessage": premium_message,
        "actionType": action_type,
    }


def _build_response_copy(generated: dict) -> dict:
    """생성된 공통 문구를 커뮤니티 응답 형식으로 변환합니다."""

    return {
        "timeScope": generated["timeScope"],
        "targetDate": generated["targetDate"],
        "headline": {
            "title": generated["headlineTitle"],
            "description": generated[
                "headlineDescription"
            ],
            "source": generated["source"],
        },
        "premiumCard": {
            "actionType": generated["actionType"],
            "message": generated["premiumMessage"],
            "subMessage": FIXED_SUB_MESSAGE,
            "targetUrl": PREMIUM_TARGET_URL,
        },
    }


def _hourly_for_date(hourly_weather: list[dict], target_date) -> list[dict]:
    result = []
    for item in hourly_weather:
        try:
            item_date = datetime.fromisoformat(item["time"]).date()
        except (KeyError, TypeError, ValueError):
            continue
        if item_date == target_date:
            result.append(item)
    return result


def _tomorrow_summary(hourly_weather: list[dict]) -> dict | None:
    if not hourly_weather:
        return None

    daytime = min(
        hourly_weather,
        key=lambda item: abs(item.get("hour", 9) - 9),
    )
    temperatures = [
        item["temperature"]
        for item in hourly_weather
        if item.get("temperature") is not None
    ]
    rainy = next(
        (
            item
            for item in hourly_weather
            if item.get("condition") in {"RAIN", "SHOWER", "SLEET", "SNOW"}
            or (item.get("precipitationProbability") or 0) >= 60
        ),
        None,
    )
    representative = rainy or daytime
    return {
        **daytime,
        "condition": representative.get("condition", "CLEAR"),
        "conditionLabel": representative.get("conditionLabel", "맑음"),
        "precipitation": 1 if rainy else 0,
        "minTemperature": min(temperatures) if temperatures else None,
        "maxTemperature": max(temperatures) if temperatures else None,
        "isNight": False,
    }


def build_community_weather_copy(*, region, grid, now=None) -> tuple[object, dict]:
    """지정한 지역의 커뮤니티 화면 문구를 생성합니다."""

    now = timezone.localtime(now) if now is not None else timezone.localtime()
    is_tomorrow = now.hour >= settings.COMMUNITY_TOMORROW_COPY_START_HOUR
    time_scope = "TOMORROW" if is_tomorrow else "TODAY"
    target_date = now.date() + timedelta(days=1 if is_tomorrow else 0)

    cache_key = (
        f"community-weather-copy:{region.region_code}:"
        f"{time_scope}:{target_date.isoformat()}"
    )

    cached = cache.get(cache_key)

    if cached is not None:
        return region, _build_response_copy(cached)

    current_weather = get_current_weather(
        grid[0],
        grid[1],
    )

    hourly_weather = get_hourly_weather(
        grid[0],
        grid[1],
        hours=36,
    )

    if is_tomorrow:
        target_hourly = _hourly_for_date(hourly_weather, target_date)
        target_weather = _tomorrow_summary(target_hourly) or current_weather
        recent_posts = []
    else:
        target_hourly = hourly_weather
        target_weather = current_weather
        recent_posts = _recent_consistent_posts(region)

    fallback = _fallback_copy(
        target_weather,
        target_hourly,
        time_scope=time_scope,
    )

    source = (
        "COMMUNITY"
        if recent_posts
        else "WEATHER"
    )

    generated = generate_community_copy(
        weather_context={
            "targetScope": time_scope,
            "targetDate": target_date.isoformat(),
            "actionType": fallback["actionType"],
            "current": target_weather if not is_tomorrow else None,
            "hourly": target_hourly,
            "outfit": build_life_info(
                target_weather,
                target_hourly,
            ).outfit_label,
        },
        recent_posts=recent_posts,
        fallback={
            "headlineTitle": fallback[
                "headlineTitle"
            ],
            "headlineDescription": fallback[
                "headlineDescription"
            ],
            "premiumMessage": fallback[
                "premiumMessage"
            ],
        },
    )

    if generated is None:
        result = {
            **fallback,
            "source": "FALLBACK",
            "timeScope": time_scope,
            "targetDate": target_date.isoformat(),
        }
    else:
        result = {
            **generated,
            # 행동 종류는 날씨 규칙으로 결정합니다.
            "actionType": fallback["actionType"],
            "source": source,
            "timeScope": time_scope,
            "targetDate": target_date.isoformat(),
        }

    cache.set(
        cache_key,
        result,
        timeout=(
            settings.COMMUNITY_WEATHER_COPY_CACHE_SECONDS
        ),
    )

    return region, _build_response_copy(result)
