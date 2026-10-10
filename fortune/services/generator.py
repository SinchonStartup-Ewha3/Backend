from fortune.models import FortuneResult


def build_fortune_result(profile, target_date):
    """
    나중에 실제 운세 계산 로직 또는 AI API로 교체할 부분입니다.
    현재는 응답 구조를 잡기 위한 임시 데이터입니다.
    """

    return {
        "title": f"{target_date:%m월 %d일} 오늘의 운세",
        "image_url": None,
        "lucky_color": "하늘색",
        "lucky_item": "손수건",
        "lucky_place": "햇빛이 잘 드는 카페",
        "detail_text": (
            "오늘은 새로운 일을 시작하기 좋은 날입니다. "
            "주변 사람의 조언을 차분하게 들어보세요."
        ),
    }


def get_or_create_fortune_result(*, user, target_date, profile=None):
    """무료 요약과 결제 후 상세풀이가 공유하는 날짜별 결과를 반환합니다."""
    profile = profile or user.fortune_profile
    result, _ = FortuneResult.objects.get_or_create(
        user=user,
        target_date=target_date,
        defaults=build_fortune_result(
            profile=profile,
            target_date=target_date,
        ),
    )
    return result
