from django.db import migrations, models


def migrate_no_notification_to_rarely(apps, schema_editor):
    PremiumProfile = apps.get_model("premium", "PremiumProfile")
    PremiumProfile.objects.filter(
        exercise_preference="NO_NOTIFICATION",
    ).update(exercise_preference="RARELY")


def migrate_rarely_to_no_notification(apps, schema_editor):
    PremiumProfile = apps.get_model("premium", "PremiumProfile")
    PremiumProfile.objects.filter(
        exercise_preference="RARELY",
    ).update(exercise_preference="NO_NOTIFICATION")


class Migration(migrations.Migration):
    dependencies = [
        ("premium", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            migrate_no_notification_to_rarely,
            migrate_rarely_to_no_notification,
        ),
        migrations.AlterField(
            model_name="premiumprofile",
            name="exercise_preference",
            field=models.CharField(
                choices=[
                    ("MORNING", "아침에 자주 해요"),
                    ("EVENING", "저녁에 자주 해요"),
                    ("GOOD_WEATHER_ONLY", "날씨가 좋을 때만 해요"),
                    ("RARELY", "운동을 자주 하지 않아요"),
                ],
                default="RARELY",
                max_length=30,
            ),
        ),
    ]
