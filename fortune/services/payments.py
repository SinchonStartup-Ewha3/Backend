from dataclasses import dataclass


class PaymentGatewayNotConfigured(Exception):
    pass


class PaymentConfirmationError(Exception):
    pass


@dataclass(frozen=True)
class PaymentConfirmation:
    payment_key: str
    order_id: str
    amount: int
    status: str


def confirm_payment(*, payment_key, order_id, amount):
    """결제사 서버 승인 API를 연결하는 경계 함수입니다.

    토스페이먼츠 등 결제사가 정해지면 이 함수 안에서 서버 간 승인 요청을
    보내고, 승인 응답으로 PaymentConfirmation을 만들어 반환해야 합니다.
    연결 전에는 절대로 결제 완료로 처리하지 않습니다.
    """
    raise PaymentGatewayNotConfigured(
        "결제사 서버 승인 API가 아직 연결되지 않았습니다."
    )
