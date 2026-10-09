import logging
from urllib.parse import unquote

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

AIR_URL = "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty"
CACHE_TIMEOUT = 60 * 30  # 측정값은 1시간마다 갱신

SIDO_SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북",
    "충청남도": "충남", "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주",
}

GRADE_ORDER = ["GOOD", "NORMAL", "BAD", "VERY_BAD"]
GRADE_LABELS = {"GOOD": "좋음", "NORMAL": "보통", "BAD": "나쁨", "VERY_BAD": "매우나쁨"}
PM10_LIMITS = (30, 80, 150)   # 좋음 / 보통 / 나쁨 상한 (㎍/㎥)
PM25_LIMITS = (15, 35, 75)


def grade_of(value: float, limits: tuple[int, int, int]) -> str:
    for grade, limit in zip(GRADE_ORDER, limits):
        if value <= limit:
            return grade
    return "VERY_BAD"


def _to_int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None  # 점검 중이면 "-" 로 온다


def _average(values: list[int | None]) -> int | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values)) if values else None


def _fetch_sido(sido: str) -> list[dict]:
    key = f"air:{sido}"
    items = cache.get(key)
    if items is None:
        resp = requests.get(
            AIR_URL,
            params={
                # 공공데이터포털 인증키는 계정당 하나라 기상청 키를 같이 쓴다
                "serviceKey": unquote(settings.KMA_SERVICE_KEY),
                "returnType": "json",
                "numOfRows": 200,
                "pageNo": 1,
                "sidoName": sido,
                "ver": "1.0",
            },
            timeout=5,
        )
        resp.raise_for_status()
        items = resp.json()["response"]["body"]["items"]
        cache.set(key, items, timeout=CACHE_TIMEOUT)
    return items


def get_air_quality(region) -> dict | None:
    """사용자 지역의 미세먼지 등급. 실패해도 화면이 막히지 않도록 None을 돌려준다."""
    if region is None:
        return None
    parts = region.region_name.split()
    sido = SIDO_SHORT.get(parts[0])
    if sido is None:
        return None

    try:
        items = _fetch_sido(sido)
    except (requests.RequestException, ValueError, KeyError, TypeError):
        logger.exception("에어코리아 조회 실패: %s", sido)
        return None

    # 서울은 측정소 이름이 구 이름과 같다. 못 찾으면 시도 평균을 쓴다.
    sigungu = parts[1] if len(parts) > 1 else None
    station = next((i for i in items if i.get("stationName") == sigungu), None)
    rows = [station] if station else items

    pm10 = _average([_to_int(r.get("pm10Value")) for r in rows])
    pm25 = _average([_to_int(r.get("pm25Value")) for r in rows])
    grades = []
    if pm10 is not None:
        grades.append(grade_of(pm10, PM10_LIMITS))
    if pm25 is not None:
        grades.append(grade_of(pm25, PM25_LIMITS))
    if not grades:
        return None

    grade = max(grades, key=GRADE_ORDER.index)  # 둘 중 더 나쁜 등급
    return {
        "grade": grade,
        "label": GRADE_LABELS[grade],
        "pm10": pm10,
        "pm25": pm25,
        "stationName": station["stationName"] if station else f"{sido} 평균",
    }