from datetime import timedelta

from premium.models import PremiumEntitlement


def revoke_unused_entitlement(purchase, occurred_at):
    """한 구매에서 아직 사용하지 않은 프리미엄 기간만 회수한다."""
    if purchase.revoked_at:
        return

    purchase.revoked_at = occurred_at
    if (
        not purchase.entitlement_started_at
        or not purchase.entitlement_expires_at
        or purchase.user is None
    ):
        return

    entitlement = (
        PremiumEntitlement.objects.select_for_update()
        .filter(user=purchase.user)
        .first()
    )
    if entitlement and entitlement.expires_at and entitlement.expires_at > occurred_at:
        unused_from = max(occurred_at, purchase.entitlement_started_at)
        unused_duration = max(
            timedelta(0),
            purchase.entitlement_expires_at - unused_from,
        )
        entitlement.expires_at = max(
            occurred_at,
            entitlement.expires_at - unused_duration,
        )
        entitlement.save(update_fields=["expires_at", "modified_at"])
