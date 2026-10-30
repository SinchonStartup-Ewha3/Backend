import hashlib
import hmac
from datetime import datetime, timedelta
from urllib.parse import parse_qs

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from fortune.models import FortunePayAppFeedbackEvent, FortunePurchase


PAYMENT_KEY_PREFIX = "payapp:"


class FortunePayAppConfigurationError(Exception):
    pass


class FortunePayAppAPIError(Exception):
    pass


class FortunePayAppFeedbackValidationError(Exception):
    pass


def validate_payapp_settings():
    required = {
        "PAYAPP_USER_ID": settings.PAYAPP_USER_ID,
        "PAYAPP_LINK_KEY": settings.PAYAPP_LINK_KEY,
        "PAYAPP_LINK_VALUE": settings.PAYAPP_LINK_VALUE,
        "PAYAPP_REQUEST_KEY": settings.PAYAPP_REQUEST_KEY,
        "PAYAPP_FORTUNE_FEEDBACK_URL": settings.PAYAPP_FORTUNE_FEEDBACK_URL,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise FortunePayAppConfigurationError(
            f"필수 PayApp 환경변수가 없습니다: {', '.join(missing)}"
        )


def create_payment_request(*, purchase, recvphone):
    validate_payapp_settings()
    if purchase.payapp_order_token is None:
        purchase.prepare_payapp_order()
        purchase.save(update_fields=["payapp_order_token"])
    order_token = purchase.payapp_order_token

    payload = {
        "cmd": "payrequest",
        "userid": settings.PAYAPP_USER_ID,
        "goodname": purchase.product_title,
        "price": str(purchase.amount),
        "recvphone": recvphone,
        "feedbackurl": settings.PAYAPP_FORTUNE_FEEDBACK_URL,
        "var1": str(order_token),
        "var2": settings.PAYAPP_FORTUNE_ORDER_TAG,
        "smsuse": "n",
        "checkretry": "y",
    }
    if settings.PAYAPP_FORTUNE_RETURN_URL:
        payload["returnurl"] = settings.PAYAPP_FORTUNE_RETURN_URL
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
        raise FortunePayAppAPIError("PayApp 결제 요청에 실패했습니다.") from exc

    if response.status_code != 200:
        raise FortunePayAppAPIError(
            "PayApp가 결제 요청을 정상 처리하지 못했습니다."
        )

    parsed = {
        key: values[0] if values else ""
        for key, values in parse_qs(
            response.text,
            keep_blank_values=True,
            encoding="utf-8",
        ).items()
    }
    if parsed.get("state") != "1":
        raise FortunePayAppAPIError(
            parsed.get("errorMessage") or "PayApp 결제 요청 생성에 실패했습니다."
        )
    if not parsed.get("mul_no") or not parsed.get("payurl"):
        raise FortunePayAppAPIError(
            "PayApp 응답에 결제요청번호 또는 결제 URL이 없습니다."
        )
    return parsed


def _feedback_time(value):
    if not value or len(value) != 14 or not value.isdigit():
        raise FortunePayAppFeedbackValidationError(
            "responsedate 형식이 올바르지 않습니다."
        )
    try:
        parsed = datetime.strptime(value, "%Y%m%d%H%M%S")
    except ValueError as exc:
        raise FortunePayAppFeedbackValidationError(
            "responsedate 형식이 올바르지 않습니다."
        ) from exc
    return timezone.make_aware(parsed, timezone.get_current_timezone())


def _verify_feedback(data):
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
        raise FortunePayAppFeedbackValidationError(
            f"PayApp 통보 필수 필드가 없습니다: {', '.join(missing)}"
        )

    merchant_checks = (
        hmac.compare_digest(str(data["userid"]), settings.PAYAPP_USER_ID),
        hmac.compare_digest(str(data["linkkey"]), settings.PAYAPP_LINK_KEY),
        hmac.compare_digest(str(data["linkval"]), settings.PAYAPP_LINK_VALUE),
    )
    if not all(merchant_checks):
        raise FortunePayAppFeedbackValidationError(
            "PayApp 판매자 연동 정보가 일치하지 않습니다."
        )

    occurred_at = _feedback_time(str(data["responsedate"]))
    expected_hash = hashlib.sha256(
        (
            settings.PAYAPP_USER_ID
            + str(data["responsedate"])
            + settings.PAYAPP_REQUEST_KEY
        ).encode("utf-8")
    ).hexdigest()
    if not hmac.compare_digest(expected_hash.lower(), str(data["hash"]).lower()):
        raise FortunePayAppFeedbackValidationError(
            "PayApp 통보 해시가 일치하지 않습니다."
        )
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
    occurred_at = _verify_feedback(data)
    try:
        price = int(data["price"])
    except (TypeError, ValueError) as exc:
        raise FortunePayAppFeedbackValidationError(
            "PayApp 결제 금액 형식이 올바르지 않습니다."
        ) from exc

    try:
        purchase = (
            FortunePurchase.objects.select_for_update(of=("self",))
            .get(payapp_order_token=data["var1"])
        )
    except (FortunePurchase.DoesNotExist, ValueError) as exc:
        raise FortunePayAppFeedbackValidationError(
            "PayApp 통보에 연결된 운세 주문이 없습니다."
        ) from exc

    mul_no = str(data["mul_no"])
    original_mul_no = str(data.get("orig_mul_no") or "")
    accepted_keys = {
        f"{PAYMENT_KEY_PREFIX}{value}"
        for value in (mul_no, original_mul_no)
        if value
    }
    if purchase.payment_key and purchase.payment_key not in accepted_keys:
        raise FortunePayAppFeedbackValidationError(
            "PayApp 결제요청번호가 일치하지 않습니다."
        )
    if str(data["var2"]) != settings.PAYAPP_FORTUNE_ORDER_TAG:
        raise FortunePayAppFeedbackValidationError(
            "PayApp 운세 상품 식별자가 일치하지 않습니다."
        )
    if (
        price != purchase.amount
        or str(data["goodname"]) != purchase.product_title
    ):
        raise FortunePayAppFeedbackValidationError(
            "PayApp 운세 상품 또는 결제 금액이 일치하지 않습니다."
        )

    _, created = FortunePayAppFeedbackEvent.objects.get_or_create(
        event_key=_event_key(data),
        defaults={
            "purchase": purchase,
            "mul_no": mul_no,
            "pay_state": str(data["pay_state"]),
            "responsedate": str(data["responsedate"]),
            "price": price,
        },
    )
    if not created:
        return True

    update_fields = []
    if purchase.payment_key is None:
        payment_key = f"{PAYMENT_KEY_PREFIX}{mul_no}"
        if FortunePurchase.objects.exclude(pk=purchase.pk).filter(
            payment_key=payment_key
        ).exists():
            raise FortunePayAppFeedbackValidationError(
                "이미 다른 주문에 연결된 PayApp 결제요청번호입니다."
            )
        purchase.payment_key = payment_key
        update_fields.append("payment_key")

    pay_state = str(data["pay_state"])
    if pay_state == "4":
        if purchase.payment_status in {
            FortunePurchase.PaymentStatus.CANCELED,
            FortunePurchase.PaymentStatus.REFUNDED,
        }:
            if update_fields:
                purchase.save(update_fields=update_fields)
            return False
        if purchase.user is None:
            raise FortunePayAppFeedbackValidationError(
                "탈퇴한 사용자의 결제에는 운세 이용권을 지급할 수 없습니다."
            )
        if purchase.payment_status != FortunePurchase.PaymentStatus.PAID:
            get_user_model().objects.select_for_update().get(pk=purchase.user_id)
            paid_on = timezone.localtime(occurred_at).date()
            latest_active_until = (
                FortunePurchase.objects.filter(
                    user_id=purchase.user_id,
                    payment_status=FortunePurchase.PaymentStatus.PAID,
                    active_until__gte=paid_on,
                )
                .exclude(pk=purchase.pk)
                .order_by("-active_until")
                .values_list("active_until", flat=True)
                .first()
            )
            active_from = paid_on
            if latest_active_until is not None:
                active_from = latest_active_until + timedelta(days=1)
            purchase.payment_status = FortunePurchase.PaymentStatus.PAID
            purchase.purchased_at = occurred_at
            purchase.active_from = active_from
            purchase.active_until = active_from + timedelta(
                days=purchase.duration_days - 1
            )
            update_fields.extend(
                [
                    "payment_status",
                    "purchased_at",
                    "active_from",
                    "active_until",
                ]
            )
    elif pay_state in {"8", "16", "32"}:
        if purchase.payment_status == FortunePurchase.PaymentStatus.PENDING:
            purchase.payment_status = FortunePurchase.PaymentStatus.CANCELED
            update_fields.append("payment_status")
    elif pay_state in {"9", "64"}:
        purchase.payment_status = (
            FortunePurchase.PaymentStatus.REFUNDED
            if purchase.payment_status == FortunePurchase.PaymentStatus.PAID
            else FortunePurchase.PaymentStatus.CANCELED
        )
        update_fields.append("payment_status")

    if update_fields:
        purchase.save(update_fields=list(dict.fromkeys(update_fields)))
    return False
