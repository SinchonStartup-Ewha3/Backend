from django.db import migrations


def set_fortune_1d_price_to_1000(apps, schema_editor):
    FortuneProduct = apps.get_model("fortune", "FortuneProduct")
    FortuneProduct.objects.filter(product_code="FORTUNE_1D").update(price=1000)


def restore_fortune_1d_price_to_990(apps, schema_editor):
    FortuneProduct = apps.get_model("fortune", "FortuneProduct")
    FortuneProduct.objects.filter(product_code="FORTUNE_1D").update(price=990)


class Migration(migrations.Migration):

    dependencies = [
        ("fortune", "0010_merge_fortune_character_and_payapp_refund"),
    ]

    operations = [
        migrations.RunPython(
            set_fortune_1d_price_to_1000,
            restore_fortune_1d_price_to_990,
        ),
    ]
