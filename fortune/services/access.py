from django.db.models import Q

from fortune.models import FortunePurchase


def usable_purchase_status_q(on_date):
    """환불 완료가 당일이어도 중지일 전까지는 이용권을 사용할 수 있다."""
    return Q(payment_status=FortunePurchase.PaymentStatus.PAID) | Q(
        payment_status=FortunePurchase.PaymentStatus.REFUNDED,
        refund_request__stop_from__gt=on_date,
    )
