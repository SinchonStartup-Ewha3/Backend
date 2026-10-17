from decimal import Decimal, ROUND_DOWN

from django.db import migrations, models


def populate_refund_snapshots(apps, schema_editor):
    PremiumRefundRequest = apps.get_model("premium", "PremiumRefundRequest")

    for refund_request in PremiumRefundRequest.objects.select_related("purchase"):
        purchase = refund_request.purchase
        starts_at = purchase.entitlement_started_at
        expires_at = purchase.entitlement_expires_at
        requested_at = refund_request.created_at

        amount = 0
        remaining_seconds = 0
        if starts_at and expires_at and starts_at < expires_at:
            unused_from = max(requested_at, starts_at)
            total = Decimal(str((expires_at - starts_at).total_seconds()))
            remaining = max(
                Decimal("0"),
                Decimal(str((expires_at - unused_from).total_seconds())),
            )
            remaining_seconds = int(remaining.to_integral_value(rounding=ROUND_DOWN))
            amount = int(
                (Decimal(purchase.amount) * remaining / total).to_integral_value(
                    rounding=ROUND_DOWN
                )
            )

        refund_request.reason = "기존 수동 환불 요청에서 이관됨"
        refund_request.requested_amount = amount
        refund_request.currency_code = purchase.currency_code
        refund_request.remaining_seconds = remaining_seconds
        refund_request.save(
            update_fields=[
                "reason",
                "requested_amount",
                "currency_code",
                "remaining_seconds",
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("premium", "0006_premiumrefundrequest"),
    ]

    operations = [
        migrations.AddField(
            model_name="premiumrefundrequest",
            name="currency_code",
            field=models.CharField(max_length=3, null=True),
        ),
        migrations.AddField(
            model_name="premiumrefundrequest",
            name="paddle_adjustment_id",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="premiumrefundrequest",
            name="reason",
            field=models.CharField(max_length=500, null=True),
        ),
        migrations.AddField(
            model_name="premiumrefundrequest",
            name="remaining_seconds",
            field=models.PositiveBigIntegerField(null=True),
        ),
        migrations.AddField(
            model_name="premiumrefundrequest",
            name="requested_amount",
            field=models.PositiveIntegerField(null=True),
        ),
        migrations.RunPython(populate_refund_snapshots, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="premiumrefundrequest",
            name="account_number",
        ),
        migrations.RemoveField(
            model_name="premiumrefundrequest",
            name="bank_name",
        ),
        migrations.RemoveField(
            model_name="premiumrefundrequest",
            name="phone_number",
        ),
        migrations.AlterField(
            model_name="premiumrefundrequest",
            name="currency_code",
            field=models.CharField(max_length=3),
        ),
        migrations.AlterField(
            model_name="premiumrefundrequest",
            name="reason",
            field=models.CharField(max_length=500),
        ),
        migrations.AlterField(
            model_name="premiumrefundrequest",
            name="remaining_seconds",
            field=models.PositiveBigIntegerField(),
        ),
        migrations.AlterField(
            model_name="premiumrefundrequest",
            name="requested_amount",
            field=models.PositiveIntegerField(),
        ),
    ]
