"""요청에서 날씨를 볼 위치를 정한다. 로그인 없이 쓰는 화면(홈·상황·커뮤니티 날씨 문구)이 함께 쓴다.

우선순위
1. 쿼리 파라미터 `regionCode` → 그 지역
2. 쿼리 파라미터 `lat`, `lng` → 그 좌표 (지역은 가장 가까운 읍면동)
3. 로그인 사용자 → 저장된 위치 (지금까지와 같음)
4. 셋 다 없으면 LOCATION_REQUIRED
"""
from dataclasses import dataclass

from core.geo import find_nearest_region, latlng_to_grid
from core.models import Region

from .weather import get_user_grid


class LocationError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status

    def to_response_data(self) -> dict:
        return {"detail": self.message, "code": self.code}


@dataclass(frozen=True)
class ResolvedLocation:
    grid: tuple[int, int]
    region: Region | None


def _parse_coordinate(value, name, low, high):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise LocationError("INVALID_LOCATION", f"{name} 값이 올바르지 않아요.")
    if not low <= number <= high:
        raise LocationError("INVALID_LOCATION", f"{name} 값이 올바르지 않아요.")
    return number


def resolve_location(request) -> ResolvedLocation:
    params = request.query_params

    region_code = params.get("regionCode", "").strip()
    if region_code:
        region = Region.objects.filter(region_code=region_code).first()
        if region is None:
            raise LocationError("INVALID_REGION", "존재하지 않는 지역 코드예요.")
        return ResolvedLocation((region.grid_nx, region.grid_ny), region)

    lat, lng = params.get("lat"), params.get("lng")
    if lat is not None or lng is not None:
        if lat is None or lng is None:
            raise LocationError("INVALID_LOCATION", "lat과 lng를 함께 보내주세요.")
        lat = _parse_coordinate(lat, "lat", -90, 90)
        lng = _parse_coordinate(lng, "lng", -180, 180)
        region = find_nearest_region(lat, lng)
        if region is None:
            raise LocationError("OUT_OF_SERVICE_AREA", "서비스하지 않는 지역이에요.")
        return ResolvedLocation(latlng_to_grid(lat, lng), region)

    user = request.user
    if user.is_authenticated:
        grid = get_user_grid(user)
        if grid is not None:
            return ResolvedLocation(grid, user.region)

    raise LocationError(
        "LOCATION_REQUIRED",
        "위치 정보가 필요해요. regionCode 또는 lat·lng를 함께 보내주세요.",
    )