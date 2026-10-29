from django.core.exceptions import ObjectDoesNotExist
from rest_framework.permissions import BasePermission

from .models import BankTransferRequest


class HasActivePremium(BasePermission):
    message = "활성 프리미엄 이용권이 필요합니다."
    code = "PREMIUM_REQUIRED"

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        try:
            entitlement = request.user.premium_entitlement
        except ObjectDoesNotExist:
            return False

        return entitlement.is_active()


class CanAccessPremiumSurvey(BasePermission):
    message = "프리미엄 이용권 또는 입금 확인 요청이 필요합니다."
    code = "PREMIUM_SURVEY_REQUIRED"

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        try:
            entitlement = request.user.premium_entitlement
        except ObjectDoesNotExist:
            entitlement = None

        if entitlement and entitlement.is_active():
            return True

        return BankTransferRequest.objects.filter(
            user=request.user,
            status=BankTransferRequest.Status.PENDING,
        ).exists()
