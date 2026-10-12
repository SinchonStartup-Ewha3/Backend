from django.db import migrations


def delete_disabled_schedules(apps, schema_editor):
    """OFF 상태였던 일정이 필드 제거 후 되살아나지 않도록 먼저 삭제한다."""

    NotificationSchedule = apps.get_model("situations", "NotificationSchedule")
    NotificationSchedule.objects.filter(is_enabled=False).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("situations", "0003_waterintake"),
    ]

    operations = [
        migrations.RunPython(
            delete_disabled_schedules,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RemoveIndex(
            model_name="notificationschedule",
            name="situations__user_id_9be357_idx",
        ),
        migrations.RemoveField(
            model_name="notificationschedule",
            name="is_enabled",
        ),
    ]
