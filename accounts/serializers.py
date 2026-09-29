# accounts/serializers.py
from rest_framework import serializers
from .models import SocialAccount


class SocialLoginSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=SocialAccount.Provider.choices)
    access_token = serializers.CharField()