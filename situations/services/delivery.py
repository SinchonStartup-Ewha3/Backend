import logging
from datetime import date

from django.conf import settings
from django.utils import timezone

from situations.models import NotificationLog, NotificationSchedule
from situations.services.onesignal import send_push_to_user


logger = logging.getLogger(__name__)


def deliver_notification(
    *,
    user,
    notification_type: str,
    target_date: date,
    dedupe_key: str,
    title: str,
    message: str,
    url: str | None = None,
    schedule: NotificationSchedule | None = None,
) -> NotificationLog:
    """
    알림을 한 번만 발송하고 결과를 NotificationLog에 기록합니다.

    같은 dedupe_key가 이미 성공한 경우에는 다시 발송하지 않습니다.
    실패한 알림은 다음 실행에서 다시 시도할 수 있습니다.
    """

    log, created = NotificationLog.objects.get_or_create(
        dedupe_key=dedupe_key,
        defaults={
            "user": user,
            "schedule": schedule,
            "notification_type": notification_type,
            "target_date": target_date,
            "title": title,
            "body": message,
            "status": NotificationLog.Status.PENDING,
        },
    )


    if not created and log.status == NotificationLog.Status.SENT:
        logger.info(
            "이미 발송된 알림이므로 건너뜁니다: %s",
            dedupe_key,
        )
        return log


    log.user = user
    log.schedule = schedule
    log.notification_type = notification_type
    log.target_date = target_date
    log.title = title
    log.body = message
    log.status = NotificationLog.Status.PENDING
    log.error_message = ""
    log.attempt_count += 1

    log.save(
        update_fields=[
            "user",
            "schedule",
            "notification_type",
            "target_date",
            "title",
            "body",
            "status",
            "error_message",
            "attempt_count",
        ]
    )

    try:
        result = send_push_to_user(
            user_id=user.pk,
            title=title,
            message=message,
            url=url,
        )

        if settings.ONESIGNAL_DRY_RUN:
            # 테스트 실행은 실제 발송 성공으로 기록하지 않습니다.
            # 나중에 DRY_RUN을 끈 뒤 같은 알림을 다시 보낼 수 있습니다.
            log.status = NotificationLog.Status.SKIPPED
            log.error_message = "Dry-run: 실제 알림을 발송하지 않았습니다."

        else:
            message_id = result.get("id")

            if message_id:
                log.status = NotificationLog.Status.SENT
                log.provider_message_id = message_id
                log.sent_at = timezone.now()
            else:
                log.status = NotificationLog.Status.SKIPPED
                log.error_message = str(
                    result.get("errors", "유효한 구독자를 찾지 못했습니다.")
                )

    except Exception as exc:
        log.status = NotificationLog.Status.FAILED
        log.error_message = str(exc)

        logger.exception(
            "알림 처리 실패: dedupe_key=%s",
            dedupe_key,
        )

    log.save(
        update_fields=[
            "status",
            "provider_message_id",
            "error_message",
            "attempt_count",
            "sent_at",
        ]
    )

    return log