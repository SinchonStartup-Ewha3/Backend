import logging
from datetime import datetime, timedelta
from urllib.parse import unquote

import requests
from django.conf import settings
from django.core.cache import cache

from home.services.kma_client import KST, now_kst

logger = logging.getLogger(__name__)

UV_URL = "https://apis.data.go.kr/1360000/LivingWthrIdxServiceV5/getUVIdxV5"
CACHE_TIMEOUT = 60 * 60
FAIL_CACHE_TIMEOUT = 60 * 10
RELEASE_LOOKBACK = 5          # 3시간씩 최대 5번(15시간) 거슬러 올라가며 발표분을 찾는다
DAY_START, DAY_END = 9, 18    # 화면에 보여줄 자외선은 낮 시간 최댓값

# (최소값, 코드, 이름) 위에서부터 처음 맞는 것
UV_GRADES = (
    (11, "DANGER", "위험"),
    (8, "VERY_HIGH", "매우높음"),
    (6, "HIGH", "높음"),
    (3, "NORMAL", "보통"),
    (0, "LOW", "낮음"),
)


class _NoData(Exception):
    pass


def uv_grade(value: int) -> tuple[str, str]:
    for minimum, code, label in UV_GRADES:
        if value >= minimum:
            return code, label
    return "LOW", "낮음"


def _request(area_no: str, time_str: str) -> dict:
    resp = requests.get(
        UV_URL,
        params={
            "serviceKey": unquote(settings.KMA_SERVICE_KEY),  # 공공데이터포털 공용 키
            "pageNo": 1,
            "numOfRows": 10,
            "dataType": "JSON",
            "areaNo": area_no,
            "time": time_str,
        },
        timeout=5,
    )
    resp.raise_for_status()
    data = resp.json()
    header = data["response"]["header"]
    if header.get("resultCode") == "03":  # 해당 발표분 데이터 없음
        raise _NoData
    if header.get("resultCode") != "00":
        raise ValueError(f"생활기상지수 API 오류: {header.get('resultMsg')}")
    return data["response"]["body"]["items"]["item"][0]


def _area_candidates(region_code: str) -> list[str]:
    """동 → 시군구 → 시도 순으로 넓혀 조회한다"""
    codes = [region_code, region_code[:5] + "00000", region_code[:2] + "00000000"]
    return list(dict.fromkeys(codes))


def _release_candidates(now: datetime) -> list[datetime]:
    base = now.replace(minute=0, second=0, microsecond=0)
    base -= timedelta(hours=base.hour % 3)
    return [base - timedelta(hours=3 * i) for i in range(RELEASE_LOOKBACK)]


def _parse(item: dict) -> list[dict]:
    released = datetime.strptime(str(item["date"])[:10], "%Y%m%d%H").replace(tzinfo=KST)
    forecast = []
    for hours in range(0, 76, 3):
        try:
            value = int(float(item.get(f"h{hours}")))
        except (TypeError, ValueError):
            continue  # 값이 비어 있는 시각
        forecast.append({"time": released + timedelta(hours=hours), "value": value})
    return forecast


def get_uv_forecast(region, now: datetime | None = None) -> list[dict] | None:
    """자외선 예측값 목록. 실패해도 러닝 화면이 막히지 않도록 None을 돌려준다."""
    if region is None:
        return None
    now = now or now_kst()
    cache_key = f"uv:{region.region_code}:{now:%Y%m%d%H}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached or None

    forecast = []
    try:
        for area_no in _area_candidates(region.region_code):
            for released in _release_candidates(now):
                try:
                    forecast = _parse(_request(area_no, released.strftime("%Y%m%d%H")))
                except _NoData:
                    continue
                if forecast:
                    break
            if forecast:
                break
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
        logger.exception("자외선지수 조회 실패: %s", region.region_code)

    # 실패도 잠깐 캐시해서 매 요청마다 여러 번 호출하지 않게 한다
    cache.set(cache_key, forecast, CACHE_TIMEOUT if forecast else FAIL_CACHE_TIMEOUT)
    return forecast or None


def summarize_uv(forecast: list[dict] | None, target_date: str | None) -> dict | None:
    """target_date 낮 시간의 최대 자외선지수"""
    if not forecast or not target_date:
        return None
    values = [
        f["value"] for f in forecast
        if f["time"].date().isoformat() == target_date and DAY_START <= f["time"].hour < DAY_END
    ]
    if not values:
        return None
    value = max(values)
    grade, label = uv_grade(value)
    return {"value": value, "grade": grade, "label": label}