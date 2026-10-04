from rest_framework import serializers
from .models import Region


class RegionSerializer(serializers.ModelSerializer):
    regionCode = serializers.CharField(source="region_code")
    regionName = serializers.CharField(source="region_name")
    shortName = serializers.SerializerMethodField()

    class Meta:
        model = Region
        fields = ["regionCode", "regionName", "shortName"]

    def get_shortName(self, obj):
        # "서울특별시 서대문구 아현동" → "서대문구 아현동"
        parts = obj.region_name.split()
        return " ".join(parts[1:]) if len(parts) > 1 else obj.region_name