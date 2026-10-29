from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("premium", "0007_paddle_prorated_refund"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BankTransferRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("depositor_name", models.CharField(max_length=30)),
                ("amount", models.PositiveIntegerField(default=2500)),
                ("currency_code", models.CharField(default="KRW", max_length=3)),
                ("status", models.CharField(choices=[("PENDING", "입금 확인 중"), ("APPROVED", "입금 승인"), ("REJECTED", "입금 거절"), ("CANCELED", "사용자 취소"), ("REFUNDED", "환불 완료")], default="PENDING", max_length=20)),
                ("entitlement_started_at", models.DateTimeField(blank=True, null=True)),
                ("entitlement_expires_at", models.DateTimeField(blank=True, null=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("refunded_at", models.DateTimeField(blank=True, null=True)),
                ("admin_note", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_bank_transfer_requests", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bank_transfer_requests", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AlterField(
            model_name="premiumrefundrequest",
            name="purchase",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="refund_request", to="premium.premiumpurchase"),
        ),
        migrations.AddField(
            model_name="premiumrefundrequest",
            name="bank_transfer_request",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="refund_request", to="premium.banktransferrequest"),
        ),
        migrations.AddConstraint(
            model_name="banktransferrequest",
            constraint=models.UniqueConstraint(condition=models.Q(("status", "PENDING")), fields=("user",), name="uniq_pending_bank_user"),
        ),
        migrations.AddConstraint(
            model_name="premiumrefundrequest",
            constraint=models.CheckConstraint(condition=models.Q(models.Q(("bank_transfer_request__isnull", True), ("purchase__isnull", False)), models.Q(("bank_transfer_request__isnull", False), ("purchase__isnull", True)), _connector="OR"), name="refund_exactly_one_payment_source"),
        ),
    ]
