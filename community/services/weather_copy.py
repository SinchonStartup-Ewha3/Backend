from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from core.geo import find_nearest_region
from home.services.life_info import build_life_info
from home.services.weather import (
    get_current_weather,
    get_hourly_weather,
    get_user_grid,
)

from community.models import Post

from .liner_client import generate_community_copy


FIXED_SUB_MESSAGE = (
    "이미 많은 사람들이 알림 기능을 사용하고 있어요"
)

PREMIUM_TARGET_URL = "/premium"


class CommunityLocationRequired(Exception):
    """사용자의 지역을 결정할 수 없을 때 발생합니다."""


def _nickname_with_suffix(nickname: str) -> str:
    """닉네임 뒤에 '님'을 한 번만 붙입니다."""

    nickname = nickname.strip()

    if nickname.endswith("님"):
        return nickname

    return f"{nickname}님"


def _resolve_region(user):
    """계정 지역을 우선 사용하고, 없으면 마지막 GPS 좌표로 찾습니다."""

    if user.region is not None:
        return user.region

    if user.last_lat is not None and user.last_lng is not None:
        return find_nearest_region(
            float(user.last_lat),
            float(user.last_lng),
        )

    return None


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
) -> dict:
    """LINER 장애 시 사용할 규칙 기반 기본 문구입니다."""

    life_info = build_life_info(
        current_weather,
        hourly_weather,
    )

    feels_like = current_weather.get("feelsLike")
    if feels_like is None:
        feels_like = current_weather.get("temperature", 15)

    humidity = current_weather.get("humidity")
    condition = current_weather.get("condition")

    if life_info.character.value == "SNOWY":
        headline_title = "눈이 내리는 오늘"
    elif life_info.umbrella_needed:
        headline_title = "비 소식이 있는 오늘"
    elif feels_like <= 5:
        headline_title = "기온이 뚝 떨어진 오늘"
    elif feels_like >= 28:
        headline_title = "기온이 크게 오른 오늘"
    else:
        headline_title = "가볍게 외출하기 좋은 오늘"

    if life_info.umbrella_needed:
        headline_description = (
            f"{life_info.outfit_label} 차림과 우산을 추천해요"
        )
        action_type = "UMBRELLA"
        premium_message = "외출 전 우산을 꼭 챙겨주세요"

    elif feels_like <= 5:
        headline_description = (
            f"{life_info.outfit_label} 차림으로 따뜻하게 입어주세요"
        )
        action_type = "COLD"
        premium_message = "오늘은 따뜻한 겉옷을 챙겨주세요"

    elif feels_like >= 28:
        headline_description = (
            f"{life_info.outfit_label}처럼 가볍게 입어주세요"
        )
        action_type = "HYDRATION"
        premium_message = "오늘은 물을 자주 마셔주세요"

    elif humidity is not None and humidity >= 75:
        headline_description = (
            f"{life_info.outfit_label} 차림을 추천해요"
        )
        action_type = "INDOOR_DRYING"
        premium_message = "오늘 빨래는 실내 건조를 추천해요"

    elif (
        humidity is not None
        and humidity <= 60
        and condition in {"CLEAR", "PARTLY_CLOUDY"}
    ):
        headline_description = (
            f"{life_info.outfit_label} 차림을 추천해요"
        )
        action_type = "LAUNDRY"
        premium_message = "오늘은 빨래하기 좋은 날씨예요"

    elif 10 <= feels_like <= 25:
        headline_description = (
            f"{life_info.outfit_label} 차림을 추천해요"
        )
        action_type = "EXERCISE"
        premium_message = "오늘은 가벼운 야외 운동을 추천해요"

    else:
        headline_description = life_info.message
        action_type = "WEATHER"
        premium_message = (
            "오늘의 날씨에 맞춰 하루를 준비해보세요"
        )

    return {
        "headlineTitle": headline_title,
        "headlineDescription": headline_description,
        "premiumMessage": premium_message,
        "actionType": action_type,
    }


def _personalize(user, generated: dict) -> dict:
    """캐시된 공통 문구 앞에 현재 사용자 닉네임을 붙입니다."""

    display_name = _nickname_with_suffix(user.nickname)

    return {
        "headline": {
            "title": (
                f"{display_name}, "
                f"{generated['headlineTitle']}"
            ),
            "description": generated[
                "headlineDescription"
            ],
            "source": generated["source"],
        },
        "premiumCard": {
            "actionType": generated["actionType"],
            "message": (
                f"{display_name}, "
                f"{generated['premiumMessage']}"
            ),
            "subMessage": FIXED_SUB_MESSAGE,
            "targetUrl": PREMIUM_TARGET_URL,
        },
    }


def build_community_weather_copy(user) -> tuple[object, dict]:
    """사용자 지역의 커뮤니티 화면 문구를 생성합니다."""

    region = _resolve_region(user)
    grid = get_user_grid(user)

    if region is None or grid is None:
        raise CommunityLocationRequired

    cache_key = (
        f"community-weather-copy:{region.region_code}"
    )

    cached = cache.get(cache_key)

    if cached is not None:
        return region, _personalize(user, cached)

    current_weather = get_current_weather(
        grid[0],
        grid[1],
    )

    hourly_weather = get_hourly_weather(
        grid[0],
        grid[1],
        hours=24,
    )

    recent_posts = _recent_consistent_posts(region)

    fallback = _fallback_copy(
        current_weather,
        hourly_weather,
    )

    source = (
        "COMMUNITY"
        if recent_posts
        else "WEATHER"
    )

    generated = generate_community_copy(
        weather_context={
            "regionName": region.region_name,
            "current": current_weather,
            "hourly": hourly_weather[:12],
            "outfit": build_life_info(
                current_weather,
                hourly_weather,
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
        }
    else:
        result = {
            **generated,
            # 행동 종류는 날씨 규칙으로 결정합니다.
            "actionType": fallback["actionType"],
            "source": source,
        }

    cache.set(
        cache_key,
        result,
        timeout=(
            settings.COMMUNITY_WEATHER_COPY_CACHE_SECONDS
        ),
    )

    return region, _personalize(user, result)