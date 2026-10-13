import hashlib
import hmac
import time

import requests
from django.conf import settings


class PaddleConfigurationError(Exception):
    pass


class PaddleAPIError(Exception):
    pass


class PaddleWebhookSignatureError(Exception):
    pass


def _api_base_url():
    if settings.PADDLE_ENVIRONMENT == "sandbox":
        return "https://sandbox-api.paddle.com"
    if settings.PADDLE_ENVIRONMENT == "live":
        return "https://api.paddle.com"
    raise PaddleConfigurationError("PADDLE_ENVIRONMENT는 sandbox 또는 live여야 합니다.")


def validate_paddle_settings(*, webhook=False):
    required = {
        "PADDLE_API_KEY": settings.PADDLE_API_KEY,
        "PADDLE_PRICE_ID": settings.PADDLE_PRICE_ID,
    }
    if webhook:
        required = {"PADDLE_WEBHOOK_SECRET": settings.PADDLE_WEBHOOK_SECRET}

    missing = [name for name, value in required.items() if not value]
    if missing:
        raise PaddleConfigurationError(
            f"필수 Paddle 환경변수가 없습니다: {', '.join(missing)}"
        )
    _api_base_url()


def create_transaction(*, purchase):
    validate_paddle_settings()
    payload = {
        "items": [{"price_id": settings.PADDLE_PRICE_ID, "quantity": 1}],
        "collection_mode": "automatic",
        "custom_data": {
            "wee_purchase_id": str(purchase.pk),
            "wee_user_id": str(purchase.user_id),
        },
    }
    try:
        response = requests.post(
            f"{_api_base_url()}/transactions",
            headers={
                "Authorization": f"Bearer {settings.PADDLE_API_KEY}",
                "Content-Type": "application/json",
                "Paddle-Version": "1",
            },
            json=payload,
            timeout=10,
        )
    except requests.RequestException as exc:
        raise PaddleAPIError("Paddle 거래 생성 요청에 실패했습니다.") from exc

    try:
        response_payload = response.json()
    except ValueError as exc:
        raise PaddleAPIError("Paddle가 올바르지 않은 응답을 반환했습니다.") from exc

    if response.status_code != 201:
        error_detail = response_payload.get("error", {}).get("detail")
        raise PaddleAPIError(error_detail or "Paddle 거래를 생성하지 못했습니다.")

    transaction = response_payload.get("data") or {}
    if not transaction.get("id"):
        raise PaddleAPIError("Paddle 거래 응답에 transaction id가 없습니다.")

    items = transaction.get("items") or []
    item = items[0] if len(items) == 1 else {}
    price = item.get("price") or {}
    unit_price = price.get("unit_price") or {}
    if (
        price.get("id") != settings.PADDLE_PRICE_ID
        or item.get("quantity") != 1
        or str(unit_price.get("amount")) != str(settings.PADDLE_PREMIUM_AMOUNT)
        or unit_price.get("currency_code") != settings.PADDLE_PREMIUM_CURRENCY
    ):
        raise PaddleAPIError("Paddle 가격 정보가 WEE Premium 설정과 일치하지 않습니다.")
    return transaction


def verify_webhook_signature(raw_body, signature_header, *, now=None, tolerance=300):
    validate_paddle_settings(webhook=True)
    if not signature_header:
        raise PaddleWebhookSignatureError("Paddle-Signature 헤더가 없습니다.")

    values = {}
    for part in signature_header.split(";"):
        key, separator, value = part.strip().partition("=")
        if separator:
            values.setdefault(key, []).append(value)

    try:
        timestamp = int(values["ts"][0])
        signatures = values["h1"]
    except (KeyError, ValueError, IndexError) as exc:
        raise PaddleWebhookSignatureError("Paddle 서명 형식이 올바르지 않습니다.") from exc

    current_timestamp = int(now if now is not None else time.time())
    if abs(current_timestamp - timestamp) > tolerance:
        raise PaddleWebhookSignatureError("Paddle Webhook 서명 시간이 허용 범위를 벗어났습니다.")

    signed_payload = str(timestamp).encode() + b":" + raw_body
    expected = hmac.new(
        settings.PADDLE_WEBHOOK_SECRET.encode(),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    if not any(hmac.compare_digest(expected, signature) for signature in signatures):
        raise PaddleWebhookSignatureError("Paddle Webhook 서명이 일치하지 않습니다.")
