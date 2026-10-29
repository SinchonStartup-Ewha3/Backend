from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from premium.models import BankTransferRequest, PremiumEntitlement


class BankTransferStateError(Exception):
    pass


@transaction.atomic
def approve_bank_transfer(transfer_request, reviewed_by):
    """입금 확인 요청을 한 번만 승인하고 이용 기간을 부여한다."""
    locked_request = (
        BankTransferRequest.objects.select_for_update()
        .select_related("user")
        .get(pk=transfer_request.pk)
    )
    if locked_request.status != BankTransferRequest.Status.PENDING:
        raise BankTransferStateError("이미 처리된 입금 요청입니다.")

    now = timezone.now()
    entitlement, _ = (
        PremiumEntitlement.objects.select_for_update()
        .get_or_create(user=locked_request.user)
    )
    if entitlement.is_active(now):
        grant_start = entitlement.expires_at
    else:
        grant_start = now
        entitlement.started_at = now

    grant_end = grant_start + timedelta(
        days=settings.PADDLE_PREMIUM_DURATION_DAYS,
    )
    entitlement.expires_at = grant_end
    entitlement.save(
        update_fields=["started_at", "expires_at", "modified_at"],
    )

    locked_request.status = BankTransferRequest.Status.APPROVED
    locked_request.reviewed_by = reviewed_by
    locked_request.reviewed_at = now
    locked_request.entitlement_started_at = grant_start
    locked_request.entitlement_expires_at = grant_end
    locked_request.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "entitlement_started_at",
            "entitlement_expires_at",
            "modified_at",
        ],
    )
    return locked_request
