from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("premium", "0008_bank_transfer_payment"),
    ]

    operations = [
        migrations.AddField(
            model_name="premiumrefundrequest",
            name="access_restored_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="premiumrefundrequest",
            name="access_suspended_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
