from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fortune", "0011_update_fortune_1d_price"),
    ]

    operations = [
        migrations.AddField(
            model_name="fortuneresult",
            name="weather_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="fortuneresult",
            name="saju_analysis",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="fortuneresult",
            name="category_fortunes",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
