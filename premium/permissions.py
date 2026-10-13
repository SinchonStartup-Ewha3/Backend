from django.core.exceptions import ObjectDoesNotExist
from rest_framework.permissions import BasePermission


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
