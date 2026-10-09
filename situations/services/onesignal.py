import logging

import requests
from django.conf import settings


logger = logging.getLogger(__name__)


def send_push_to_user(
    *,
    user_id: int | str,
    title: str,
    message: str,
    url: str | None = None,
) -> dict:
    """
    Django 사용자 한 명에게 OneSignal 웹 푸시를 전송합니다.

    프론트에서 OneSignal.login(String(userId))을 호출하기 때문에
    Django 사용자 PK를 OneSignal external_id로 사용합니다.
    """

    if not settings.ONESIGNAL_APP_ID:
        raise ValueError("ONESIGNAL_APP_ID가 설정되지 않았습니다.")

    if not settings.ONESIGNAL_REST_API_KEY:
        raise ValueError("ONESIGNAL_REST_API_KEY가 설정되지 않았습니다.")

    if not title.strip() or not message.strip():
        raise ValueError("알림 제목과 내용은 비어 있을 수 없습니다.")

    payload = {
        "app_id": settings.ONESIGNAL_APP_ID,
        "target_channel": "push",


        "include_aliases": {
            "external_id": [str(user_id)],
        },

  
        "headings": {
            "ko": title,
            "en": title,
        },
        "contents": {
            "ko": message,
            "en": message,
        },
    }


    if url:
        payload["url"] = url


    if settings.ONESIGNAL_DRY_RUN:
        logger.info(
            "OneSignal dry run: user_id=%s, title=%s",
            user_id,
            title,
        )
        return {
            "dry_run": True,
            "target_user_id": str(user_id),
            "title": title,
            "message": message,
            "url": url,
        }

    headers = {
        "Authorization": f"Key {settings.ONESIGNAL_REST_API_KEY}",
        "Content-Type": "application/json; charset=utf-8",
    }

    try:
        response = requests.post(
            settings.ONESIGNAL_API_URL,
            headers=headers,
            json=payload,
            timeout=10,
        )
        response.raise_for_status()

    except requests.RequestException as exc:
        logger.exception(
            "OneSignal 알림 발송 실패: user_id=%s",
            user_id,
        )
        raise RuntimeError("OneSignal 알림 발송에 실패했습니다.") from exc


    return response.json()