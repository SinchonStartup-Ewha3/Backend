from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from situations.services.scheduler import (
    send_daily_preference_notifications,
    send_due_outing_notifications,
)


class Command(BaseCommand):
    help = "현재 시각에 발송할 맞춤 날씨 알림을 처리합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--now",
            type=str,
            help="테스트 기준 시각. 예: 2026-10-08T07:00",
        )

    def handle(self, *args, **options):
        now = self._parse_now(options.get("now"))

        self.stdout.write(
            f"알림 처리 시작: {timezone.localtime(now):%Y-%m-%d %H:%M:%S}"
        )

        outing_result = send_due_outing_notifications(now=now)
        preference_result = send_daily_preference_notifications(now=now)

        self.stdout.write(
            "외출 알림 결과: "
            f"확인={outing_result['checked']}, "
            f"발송시각 도달={outing_result['due']}, "
            f"처리={outing_result['processed']}, "
            f"오류={outing_result['errors']}"
        )

        self.stdout.write(
            "운동·빨래 알림 결과: "
            f"확인={preference_result['checked']}, "
            f"운동 처리={preference_result['exercise_processed']}, "
            f"빨래 처리={preference_result['laundry_processed']}, "
            f"조건 제외={preference_result['skipped']}, "
            f"오류={preference_result['errors']}"
        )

        total_errors = (
            outing_result["errors"]
            + preference_result["errors"]
        )

        if total_errors:
            raise CommandError(
                f"알림 처리 중 {total_errors}건의 오류가 발생했습니다."
            )

        self.stdout.write(
            self.style.SUCCESS("맞춤 날씨 알림 처리가 완료되었습니다.")
        )

    def _parse_now(self, value: str | None) -> datetime:
        if not value:
            return timezone.now()

        parsed = parse_datetime(value)

        if parsed is None:
            raise CommandError(
                "--now 형식이 올바르지 않습니다. "
                "예: 2026-10-08T07:00"
            )

        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(
                parsed,
                timezone.get_current_timezone(),
            )

        return parsed