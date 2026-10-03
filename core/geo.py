import math
from decimal import Decimal

from .models import Region

# 기상청 단기예보 격자 변환 상수 (Lambert Conformal Conic 투영)
RE = 6371.00877   # 지구 반경(km)
GRID = 5.0        # 격자 간격(km)
SLAT1 = 30.0      # 투영 위도1
SLAT2 = 60.0      # 투영 위도2
OLON = 126.0      # 기준점 경도
OLAT = 38.0       # 기준점 위도
XO = 43           # 기준점 X좌표(격자)
YO = 136          # 기준점 Y좌표(격자)


def latlng_to_grid(lat: float, lng: float) -> tuple[int, int]:
    """위경도를 기상청 격자 좌표(nx, ny)로 변환한다."""
    degrad = math.pi / 180.0
    re = RE / GRID
    slat1, slat2 = SLAT1 * degrad, SLAT2 * degrad
    olon, olat = OLON * degrad, OLAT * degrad

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = math.pow(sf, sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / math.pow(ro, sn)

    ra = math.tan(math.pi * 0.25 + float(lat) * degrad * 0.5)
    ra = re * sf / math.pow(ra, sn)
    theta = float(lng) * degrad - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn

    nx = math.floor(ra * math.sin(theta) + XO + 0.5)
    ny = math.floor(ro - ra * math.cos(theta) + YO + 0.5)
    return nx, ny


def _distance_km(lat1, lng1, lat2, lng2) -> float:
    """두 지점 사이 거리(km, 하버사인 공식)."""
    lat1, lng1, lat2, lng2 = map(lambda v: math.radians(float(v)), (lat1, lng1, lat2, lng2))
    a = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2)
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def find_nearest_region(lat, lng, max_km: float = 20.0) -> Region | None:
    """가장 가까운 읍면동 단위 Region을 찾는다. 국내가 아니면 None."""
    lat, lng = Decimal(str(lat)), Decimal(str(lng))

    # 검색 범위를 점점 넓혀가며 후보를 찾는다 (약 5km → 11km → 22km)
    for delta in (Decimal("0.05"), Decimal("0.1"), Decimal("0.2")):
        candidates = (
            Region.objects
            .filter(
                lat__range=(lat - delta, lat + delta),
                lng__range=(lng - delta, lng + delta),
            )
            .exclude(region_code__endswith="00000")  # 시도·시군구 대표 행 제외
        )
        if candidates:
            nearest = min(candidates, key=lambda r: _distance_km(lat, lng, r.lat, r.lng))
            if _distance_km(lat, lng, nearest.lat, nearest.lng) <= max_km:
                return nearest
            return None
    return None