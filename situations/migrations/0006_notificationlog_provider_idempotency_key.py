import uuid

from django.db import migrations, models


def populate_provider_idempotency_keys(apps, schema_editor):
    NotificationLog = apps.get_model("situations", "NotificationLog")

    for notification_log in NotificationLog.objects.iterator():
        notification_log.provider_idempotency_key = uuid.uuid4()
        notification_log.save(update_fields=["provider_idempotency_key"])


class Migration(migrations.Migration):

    dependencies = [
        ("situations", "0005_alter_notificationlog_notification_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationlog",
            name="provider_idempotency_key",
            field=models.UUIDField(
                editable=False,
                null=True,
            ),
        ),
        migrations.RunPython(
            populate_provider_idempotency_keys,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="notificationlog",
            name="provider_idempotency_key",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
            ),
        ),
    ]
