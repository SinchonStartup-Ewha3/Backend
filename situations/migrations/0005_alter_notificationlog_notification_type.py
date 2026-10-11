from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("situations", "0004_remove_notificationschedule_is_enabled"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notificationlog",
            name="notification_type",
            field=models.CharField(
                choices=[
                    ("OUTING_WEATHER", "외출 날씨"),
                    ("OUTERWEAR", "겉옷"),
                    ("EXERCISE", "운동"),
                    ("LAUNDRY", "빨래"),
                    ("FORTUNE", "운세"),
                ],
                max_length=30,
            ),
        ),
    ]
