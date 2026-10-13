from django.db import transaction
from django.utils import timezone

from premium.models import PremiumPurchase, PremiumRefundRequest

from .entitlements import revoke_unused_entitlement


class RefundRequestStateError(Exception):
    pass


@transaction.atomic
def complete_manual_refund(refund_request, *, completed_at=None):
    """계좌 송금 완료 후 구매 상태와 아직 사용하지 않은 이용 기간을 정리한다."""
    completed_at = completed_at or timezone.now()
    locked_request = (
        PremiumRefundRequest.objects.select_for_update()
        .select_related("purchase")
        .get(pk=refund_request.pk)
    )
    if locked_request.status == PremiumRefundRequest.Status.COMPLETED:
        return locked_request
    if locked_request.status == PremiumRefundRequest.Status.REJECTED:
        raise RefundRequestStateError("거절된 환불 요청은 완료 처리할 수 없습니다.")

    purchase = PremiumPurchase.objects.select_for_update().get(
        pk=locked_request.purchase_id
    )
    revoke_unused_entitlement(purchase, completed_at)
    purchase.status = PremiumPurchase.Status.REFUNDED
    purchase.save(update_fields=["status", "revoked_at", "modified_at"])

    locked_request.status = PremiumRefundRequest.Status.COMPLETED
    locked_request.completed_at = completed_at
    locked_request.rejection_reason = ""
    locked_request.save(
        update_fields=[
            "status",
            "completed_at",
            "rejection_reason",
            "modified_at",
        ]
    )
    return locked_request
