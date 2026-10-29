import hashlib
import hmac
from datetime import datetime
from urllib.parse import parse_qs

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from premium.models import PayAppFeedbackEvent, PayAppPayment

from .entitlements import grant_entitlement


class PayAppConfigurationError(Exception):
    pass


class PayAppAPIError(Exception):
    pass


class PayAppFeedbackValidationError(Exception):
    pass


def validate_payapp_settings():
    required = {
        "PAYAPP_USER_ID": settings.PAYAPP_USER_ID,
        "PAYAPP_LINK_KEY": settings.PAYAPP_LINK_KEY,
        "PAYAPP_LINK_VALUE": settings.PAYAPP_LINK_VALUE,
        "PAYAPP_REQUEST_KEY": settings.PAYAPP_REQUEST_KEY,
        "PAYAPP_FEEDBACK_URL": settings.PAYAPP_FEEDBACK_URL,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise PayAppConfigurationError(
            f"필수 PayApp 환경변수가 없습니다: {', '.join(missing)}"
        )


def mask_phone(phone):
    return f"***-****-{phone[-4:]}"


def create_payment_request(*, payment, recvphone):
    validate_payapp_settings()
    payload = {
        "cmd": "payrequest",
        "userid": settings.PAYAPP_USER_ID,
        "goodname": settings.PAYAPP_PRODUCT_NAME,
        "price": str(settings.PAYAPP_PREMIUM_AMOUNT),
        "recvphone": recvphone,
        "feedbackurl": settings.PAYAPP_FEEDBACK_URL,
        "var1": str(payment.order_token),
        "var2": settings.PAYAPP_ORDER_TAG,
        "smsuse": "n",
        "checkretry": "y",
    }
    if settings.PAYAPP_RETURN_URL:
        payload["returnurl"] = settings.PAYAPP_RETURN_URL
        payload["skip_cstpage"] = "y"
    if settings.PAYAPP_OPEN_PAY_TYPE:
        payload["openpaytype"] = settings.PAYAPP_OPEN_PAY_TYPE

    try:
        response = requests.post(
            settings.PAYAPP_API_URL,
            data=payload,
            timeout=settings.PAYAPP_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise PayAppAPIError("PayApp 결제 요청에 실패했습니다.") from exc

    if response.status_code != 200:
        raise PayAppAPIError("PayApp가 결제 요청을 정상 처리하지 못했습니다.")

    parsed = {
        key: values[0] if values else ""
        for key, values in parse_qs(
            response.text,
            keep_blank_values=True,
            encoding="utf-8",
        ).items()
    }
    if parsed.get("state") != "1":
        raise PayAppAPIError(
            parsed.get("errorMessage") or "PayApp 결제 요청 생성에 실패했습니다."
        )
    if not parsed.get("mul_no") or not parsed.get("payurl"):
        raise PayAppAPIError("PayApp 응답에 결제요청번호 또는 결제 URL이 없습니다.")
    return parsed


def _feedback_time(value):
    if not value or len(value) != 14 or not value.isdigit():
        raise PayAppFeedbackValidationError("responsedate 형식이 올바르지 않습니다.")
    try:
        parsed = datetime.strptime(value, "%Y%m%d%H%M%S")
    except ValueError as exc:
        raise PayAppFeedbackValidationError(
            "responsedate 형식이 올바르지 않습니다."
        ) from exc
    return timezone.make_aware(parsed, timezone.get_current_timezone())


def verify_feedback(data):
    required = {
        "userid",
        "linkkey",
        "linkval",
        "responsedate",
        "hash",
        "goodname",
        "price",
        "pay_state",
        "var1",
        "var2",
        "mul_no",
    }
    missing = sorted(name for name in required if not data.get(name))
    if missing:
        raise PayAppFeedbackValidationError(
            f"PayApp 통보 필수 필드가 없습니다: {', '.join(missing)}"
        )

    merchant_checks = (
        hmac.compare_digest(str(data["userid"]), settings.PAYAPP_USER_ID),
        hmac.compare_digest(str(data["linkkey"]), settings.PAYAPP_LINK_KEY),
        hmac.compare_digest(str(data["linkval"]), settings.PAYAPP_LINK_VALUE),
    )
    if not all(merchant_checks):
        raise PayAppFeedbackValidationError("PayApp 판매자 연동 정보가 일치하지 않습니다.")

    occurred_at = _feedback_time(str(data["responsedate"]))
    expected_hash = hashlib.sha256(
        (
            settings.PAYAPP_USER_ID
            + str(data["responsedate"])
            + settings.PAYAPP_REQUEST_KEY
        ).encode("utf-8")
    ).hexdigest()
    if not hmac.compare_digest(expected_hash.lower(), str(data["hash"]).lower()):
        raise PayAppFeedbackValidationError("PayApp 통보 해시가 일치하지 않습니다.")
    return occurred_at


def _event_key(data):
    fields = (
        "mul_no",
        "orig_mul_no",
        "pay_state",
        "responsedate",
        "price",
        "var1",
        "var2",
        "canceldate",
    )
    canonical = "\x1f".join(str(data.get(field, "")) for field in fields)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@transaction.atomic
def process_feedback(data):
    occurred_at = verify_feedback(data)
    try:
        price = int(data["price"])
    except (TypeError, ValueError) as exc:
        raise PayAppFeedbackValidationError(
            "PayApp 결제 금액 형식이 올바르지 않습니다."
        ) from exc

    try:
        payment = (
            PayAppPayment.objects.select_for_update()
            .select_related("user")
            .get(order_token=data["var1"])
        )
    except (PayAppPayment.DoesNotExist, ValueError) as exc:
        raise PayAppFeedbackValidationError(
            "PayApp 통보에 연결된 WEE 주문이 없습니다."
        ) from exc

    if payment.mul_no != str(data["mul_no"]) and payment.mul_no != str(
        data.get("orig_mul_no") or ""
    ):
        raise PayAppFeedbackValidationError("PayApp 결제요청번호가 일치하지 않습니다.")
    if str(data["var2"]) != settings.PAYAPP_ORDER_TAG:
        raise PayAppFeedbackValidationError("PayApp 상품 식별자가 일치하지 않습니다.")
    if (
        price != payment.amount
        or price != settings.PAYAPP_PREMIUM_AMOUNT
        or str(data["goodname"]) != payment.product_name
        or payment.product_name != settings.PAYAPP_PRODUCT_NAME
    ):
        raise PayAppFeedbackValidationError("PayApp 상품 또는 결제 금액이 일치하지 않습니다.")

    _, created = PayAppFeedbackEvent.objects.get_or_create(
        event_key=_event_key(data),
        defaults={
            "payment": payment,
            "mul_no": str(data["mul_no"]),
            "pay_state": str(data["pay_state"]),
            "responsedate": str(data["responsedate"]),
            "price": price,
        },
    )
    if not created:
        return True

    pay_state = str(data["pay_state"])
    payment.provider_state = pay_state
    update_fields = ["provider_state", "modified_at"]

    if pay_state == "4":
        if payment.status in {
            PayAppPayment.Status.REQUEST_CANCELED,
            PayAppPayment.Status.APPROVAL_CANCELED,
        }:
            payment.save(update_fields=update_fields)
            return False
        if payment.user is None:
            raise PayAppFeedbackValidationError(
                "탈퇴한 사용자의 결제에는 권한을 지급할 수 없습니다."
            )
        if payment.entitlement_expires_at is None:
            grant_start, grant_end = grant_entitlement(
                user=payment.user,
                occurred_at=occurred_at,
                duration_days=settings.PAYAPP_PREMIUM_DURATION_DAYS,
            )
            payment.entitlement_started_at = grant_start
            payment.entitlement_expires_at = grant_end
            payment.completed_at = occurred_at
            payment.status = PayAppPayment.Status.COMPLETED
            payment.failure_reason = ""
            update_fields.extend(
                [
                    "entitlement_started_at",
                    "entitlement_expires_at",
                    "completed_at",
                    "status",
                    "failure_reason",
                ]
            )
    elif pay_state == "10" and payment.entitlement_expires_at is None:
        payment.status = PayAppPayment.Status.WAITING
        update_fields.append("status")
    elif pay_state in {"8", "16", "32"} and payment.entitlement_expires_at is None:
        payment.status = PayAppPayment.Status.REQUEST_CANCELED
        payment.provider_canceled_at = occurred_at
        update_fields.extend(["status", "provider_canceled_at"])
    elif pay_state in {"9", "64"}:
        payment.status = PayAppPayment.Status.APPROVAL_CANCELED
        payment.provider_canceled_at = occurred_at
        update_fields.extend(["status", "provider_canceled_at"])
    elif pay_state in {"70", "71"}:
        payment.status = PayAppPayment.Status.PARTIALLY_CANCELED
        payment.provider_canceled_at = occurred_at
        update_fields.extend(["status", "provider_canceled_at"])

    payment.save(update_fields=list(dict.fromkeys(update_fields)))
    return False
