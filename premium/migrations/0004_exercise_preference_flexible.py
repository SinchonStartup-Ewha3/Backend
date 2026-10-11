from django.db import migrations, models


def forwards(apps, schema_editor):
    PremiumProfile = apps.get_model("premium", "PremiumProfile")
    PremiumProfile.objects.filter(exercise_preference="RARELY").update(
        exercise_preference="FLEXIBLE"
    )


def backwards(apps, schema_editor):
    PremiumProfile = apps.get_model("premium", "PremiumProfile")
    PremiumProfile.objects.filter(exercise_preference="FLEXIBLE").update(
        exercise_preference="RARELY"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("premium", "0003_notificationpreference"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=backwards),
        migrations.AlterField(
            model_name="premiumprofile",
            name="exercise_preference",
            field=models.CharField(
                choices=[
                    ("MORNING", "아침에 자주 해요"),
                    ("EVENING", "저녁에 자주 해요"),
                    ("GOOD_WEATHER_ONLY", "날씨가 좋을 때만 해요"),
                    ("FLEXIBLE", "정해진 시간은 없어요"),
                ],
                default="FLEXIBLE",
                max_length=30,
            ),
        ),
    ]
