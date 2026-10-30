import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fortune", "0008_fortune_payapp"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FortuneRefundRequest",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("reason", models.CharField(max_length=500)),
                ("requested_amount", models.PositiveIntegerField()),
                ("currency_code", models.CharField(default="KRW", max_length=3)),
                ("unused_days", models.PositiveSmallIntegerField()),
                ("requested_on", models.DateField()),
                ("stop_from", models.DateField()),
                ("original_active_until", models.DateField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("REQUESTED", "요청됨"),
                            ("PROCESSING", "처리 중"),
                            ("COMPLETED", "환불 완료"),
                            ("REJECTED", "거절"),
                        ],
                        default="REQUESTED",
                        max_length=20,
                    ),
                ),
                ("rejection_reason", models.CharField(blank=True, max_length=500)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("rejected_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                (
                    "purchase",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="refund_request",
                        to="fortune.fortunepurchase",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="fortune_refund_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
