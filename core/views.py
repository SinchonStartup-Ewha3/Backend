from django.shortcuts import render

from rest_framework import generics
from rest_framework.exceptions import ValidationError

from .models import Region
from .serializers import RegionSerializer


class RegionSearchView(generics.ListAPIView):
    """직접 위치 설정 화면의 지역 검색"""

    serializer_class = RegionSerializer
    pagination_class = None

    def get_queryset(self):
        q = self.request.query_params.get("q", "").strip()
        if len(q) < 2:
            raise ValidationError({"q": "검색어를 2글자 이상 입력해주세요."})

        queryset = Region.objects.exclude(region_code__endswith="00000000")  # 시도만 제외
        for token in q.split():
            queryset = queryset.filter(region_name__contains=token)
        return queryset.order_by("region_code")[:20]