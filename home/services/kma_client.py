from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.core.cache import cache
from urllib.parse import unquote 

KST = ZoneInfo("Asia/Seoul")
# 환경별로 엔드포인트를 바꿀 수 있도록 settings에서 읽는다.
BASE_URL = settings.KMA_BASE_URL.rstrip("/")
VILAGE_BASE_HOURS = (2, 5, 8, 11, 14, 17, 20, 23)
CACHE_TIMEOUT = 60 * 60 * 3  # 3시간


class KmaApiError(Exception):
    pass


def now_kst() -> datetime:
    return datetime.now(KST)


def ultra_srt_ncst_base(now: datetime) -> tuple[str, str]:
    """초단기실황: 매시 정각 발표, 40분 이후부터 조회 가능"""
    base = now if now.minute >= 40 else now - timedelta(hours=1)
    return base.strftime("%Y%m%d"), base.strftime("%H00")


def vilage_fcst_base(now: datetime) -> tuple[str, str]:
    """단기예보: 02시부터 3시간 간격 발표, 발표 10분 후 제공 (여유 있게 15분)"""
    for hour in reversed(VILAGE_BASE_HOURS):
        released = now.replace(hour=hour, minute=15, second=0, microsecond=0)
        if now >= released:
            return now.strftime("%Y%m%d"), f"{hour:02d}00"
    yesterday = now - timedelta(days=1)
    return yesterday.strftime("%Y%m%d"), "2300"


def daily_minmax_base(now: datetime) -> tuple[str, str]:
    """오늘 최저(06시)·최고(15시)가 모두 들어 있는 발표: 오늘 02시, 그 전이면 어제 23시"""
    if now >= now.replace(hour=2, minute=15, second=0, microsecond=0):
        return now.strftime("%Y%m%d"), "0200"
    return (now - timedelta(days=1)).strftime("%Y%m%d"), "2300"


def _request(operation: str, base_date: str, base_time: str, nx: int, ny: int) -> list[dict]:
    if not settings.KMA_SERVICE_KEY:
        raise KmaApiError("기상청 서비스 키가 설정되지 않았습니다.")

    params = {
        "serviceKey": unquote(settings.KMA_SERVICE_KEY),
        "pageNo": 1,
        "numOfRows": 1000,
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny,
    }
    try:
        resp = requests.get(f"{BASE_URL}/{operation}", params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except ValueError as e:
        # 서비스 키 오류 등은 JSON이 아니라 XML로 응답이 온다
        raise KmaApiError("기상청 응답을 해석할 수 없습니다. 서비스 키를 확인해주세요.") from e
    except requests.HTTPError as e:
        raise KmaApiError(
            f"기상청 API 요청이 거부되었습니다({resp.status_code}). 서비스 키를 확인해주세요."
        ) from e
    except requests.RequestException as e:
        raise KmaApiError("기상청 서버와 통신에 실패했습니다.") from e

    header = data.get("response", {}).get("header", {})
    if header.get("resultCode") != "00":
        raise KmaApiError(f"기상청 API 오류: {header.get('resultMsg')}")
    return data["response"]["body"]["items"]["item"]


def fetch_items(operation: str, base_date: str, base_time: str, nx: int, ny: int) -> list[dict]:
    """같은 격자·같은 발표분은 캐시에서 돌려준다"""
    key = f"kma:{operation}:{nx}:{ny}:{base_date}{base_time}"
    items = cache.get(key)
    if items is None:
        items = _request(operation, base_date, base_time, nx, ny)
        cache.set(key, items, timeout=CACHE_TIMEOUT)
    return items
