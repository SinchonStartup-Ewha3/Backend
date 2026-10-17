import csv
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from fortune.models import FortuneCoupon, FortuneProduct
from fortune.services.coupons import CODE_ALPHABET, generate_code


class Command(BaseCommand):
    help = "굿즈 카드에 인쇄할 운세 이용권 코드를 만들고 CSV로 저장합니다."

    def add_arguments(self, parser):
        parser.add_argument("--product", required=True, help="상품 코드 (예: FORTUNE_7D)")
        parser.add_argument("--count", type=int, required=True, help="만들 코드 개수")
        parser.add_argument("--length", type=int, default=settings.FORTUNE_COUPON_CODE_LENGTH)
        parser.add_argument("--expires", help="사용 기한 YYYY-MM-DD (비우면 무기한)")
        parser.add_argument("--batch", default="", help="발급 묶음 이름 (예: 10월 축제)")
        parser.add_argument("--output", default="fortune_coupons.csv", help="저장할 CSV 경로")

    def handle(self, *args, **options):
        try:
            product = FortuneProduct.objects.get(product_code=options["product"])
        except FortuneProduct.DoesNotExist:
            codes = ", ".join(FortuneProduct.objects.values_list("product_code", flat=True))
            raise CommandError(f"상품 코드가 없습니다. 사용 가능: {codes}")

        count, length = options["count"], options["length"]
        if count <= 0:
            raise CommandError("--count는 1 이상이어야 합니다.")
        # 조합 수의 1% 이상을 쓰면 아무 코드나 넣어도 맞을 확률이 너무 높아진다.
        capacity = len(CODE_ALPHABET) ** length
        used = FortuneCoupon.objects.filter(code__regex=rf"^[A-Z0-9]{{{length}}}$").count()
        if used + count > capacity // 100:
            raise CommandError(
                f"{length}자리 코드는 최대 {capacity // 100}개까지만 발급할 수 있어요. "
                "--length를 늘려주세요."
            )

        expires_on = date.fromisoformat(options["expires"]) if options["expires"] else None

        existing = set(FortuneCoupon.objects.values_list("code", flat=True))
        new_codes = set()
        while len(new_codes) < count:
            code = generate_code(length)
            if code not in existing:
                new_codes.add(code)

        FortuneCoupon.objects.bulk_create(
            FortuneCoupon(
                code=code,
                product=product,
                batch_label=options["batch"],
                expires_on=expires_on,
            )
            for code in sorted(new_codes)
        )

        with open(options["output"], "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["code", "product", "expires_on", "batch"])
            for code in sorted(new_codes):
                writer.writerow([code, product.product_code, expires_on or "", options["batch"]])

        self.stdout.write(self.style.SUCCESS(
            f"{product.title} 코드 {count}개를 만들어 {options['output']}에 저장했습니다."
        ))