from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("community", "0003_post_region"),
    ]

    operations = [
        migrations.AlterField(
            model_name="post",
            name="tag",
            field=models.CharField(
                choices=[
                    ("cardigan", "가디건"),
                    ("padded", "패딩"),
                    ("coat", "코트"),
                    ("other", "기타"),
                ],
                max_length=10,
            ),
        ),
    ]
