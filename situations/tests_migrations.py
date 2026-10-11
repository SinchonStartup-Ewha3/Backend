from datetime import date, time

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from core.models import Region


class RemoveNotificationScheduleEnabledMigrationTests(TransactionTestCase):
    migrate_from = ("situations", "0003_waterintake")
    migrate_to = ("situations", "0004_remove_notificationschedule_is_enabled")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps

        NotificationSchedule = old_apps.get_model(
            "situations",
            "NotificationSchedule",
        )

        region = Region.objects.create(
            region_code="migration-test-region",
            region_name="서울특별시 테스트구",
            lat="37.500000",
            lng="127.000000",
            grid_nx=60,
            grid_ny=127,
        )
        user = get_user_model().objects.create(
            nickname="일정마이그레이션사용자",
        )
        self.enabled_schedule_id = NotificationSchedule.objects.create(
            user_id=user.pk,
            region_id=region.pk,
            name="유지할 일정",
            weekdays=[0],
            outing_time=time(8, 0),
            is_enabled=True,
        ).pk
        self.disabled_schedule_id = NotificationSchedule.objects.create(
            user_id=user.pk,
            region_id=region.pk,
            name="삭제할 일정",
            weekdays=[1],
            outing_time=time(9, 0),
            is_enabled=False,
        ).pk

    def tearDown(self):
        MigrationExecutor(connection).migrate([self.migrate_to])
        super().tearDown()

    def test_disabled_schedule_is_deleted_before_enabled_field_is_removed(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        new_apps = executor.loader.project_state([self.migrate_to]).apps
        NotificationSchedule = new_apps.get_model(
            "situations",
            "NotificationSchedule",
        )

        self.assertTrue(
            NotificationSchedule.objects.filter(
                pk=self.enabled_schedule_id,
            ).exists()
        )
        self.assertFalse(
            NotificationSchedule.objects.filter(
                pk=self.disabled_schedule_id,
            ).exists()
        )


class ProviderIdempotencyKeyMigrationTests(TransactionTestCase):
    migrate_from = (
        "situations",
        "0005_alter_notificationlog_notification_type",
    )
    migrate_to = (
        "situations",
        "0006_notificationlog_provider_idempotency_key",
    )

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps

        NotificationLog = old_apps.get_model(
            "situations",
            "NotificationLog",
        )
        user = get_user_model().objects.create(
            nickname="알림로그마이그레이션사용자",
        )

        for index in range(2):
            NotificationLog.objects.create(
                user_id=user.pk,
                notification_type="OUTERWEAR",
                target_date=date(2026, 10, 10),
                dedupe_key=f"migration-log-{index}",
                title="마이그레이션 테스트",
                body="기존 발송 로그입니다.",
            )

    def tearDown(self):
        MigrationExecutor(connection).migrate([self.migrate_to])
        super().tearDown()

    def test_existing_logs_receive_unique_provider_keys(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        new_apps = executor.loader.project_state([self.migrate_to]).apps
        NotificationLog = new_apps.get_model(
            "situations",
            "NotificationLog",
        )

        provider_keys = list(
            NotificationLog.objects.order_by("pk").values_list(
                "provider_idempotency_key",
                flat=True,
            )
        )

        self.assertEqual(len(provider_keys), 2)
        self.assertTrue(all(provider_keys))
        self.assertEqual(len(set(provider_keys)), 2)
