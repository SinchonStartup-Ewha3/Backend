from django.db import migrations


PRODUCTS = [
    {
        "product_code": "FORTUNE_1D",
        "title": "오늘의 운세 1일",
        "description": "오늘 하루의 상세 풀이를 확인해요.",
        "price": 990,
        "duration_days": 1,
        "display_order": 1,
    },
    {
        "product_code": "FORTUNE_7D",
        "title": "오늘의 운세 7일",
        "description": "7일 동안 매일 상세 풀이를 확인해요.",
        "price": 5900,
        "duration_days": 7,
        "display_order": 2,
    },
    {
        "product_code": "FORTUNE_14D",
        "title": "오늘의 운세 14일",
        "description": "14일 동안 매일 상세 풀이를 확인해요.",
        "price": 11600,
        "duration_days": 14,
        "display_order": 3,
    },
    {
        "product_code": "FORTUNE_21D",
        "title": "오늘의 운세 21일",
        "description": "21일 동안 매일 상세 풀이를 확인해요.",
        "price": 16000,
        "duration_days": 21,
        "display_order": 4,
    },
]


def seed_products(apps, schema_editor):
    fortune_product = apps.get_model("fortune", "FortuneProduct")
    for product in PRODUCTS:
        fortune_product.objects.update_or_create(
            product_code=product["product_code"],
            defaults=product,
        )


def remove_products(apps, schema_editor):
    fortune_product = apps.get_model("fortune", "FortuneProduct")
    fortune_product.objects.filter(
        product_code__in=[product["product_code"] for product in PRODUCTS]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("fortune", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_products, remove_products),
    ]
