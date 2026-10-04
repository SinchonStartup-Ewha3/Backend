import uuid
from dataclasses import dataclass

import requests
from django.db import transaction

from .models import User, SocialAccount
from .models import TEMP_NICKNAME_PREFIX


class SocialAuthError(Exception):
    def __init__(self, message, status_code=401):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class SocialProfile:
    provider_uid: str
    nickname: str | None
    profile_image: str | None
    email: str | None = None


def get_kakao_profile(access_token: str) -> SocialProfile:
    try:
        resp = requests.get(
            "https://kapi.kakao.com/v2/user/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=5,
        )
    except requests.RequestException as e:
        raise SocialAuthError("카카오 서버와 통신에 실패했습니다.", status_code=502) from e

    if resp.status_code != 200:
        raise SocialAuthError("유효하지 않은 카카오 토큰입니다.")

    data = resp.json()
    account = data.get("kakao_account", {})
    profile = account.get("profile", {})
    return SocialProfile(
        provider_uid=str(data["id"]),
        nickname=profile.get("nickname"),
        profile_image=profile.get("profile_image_url"),
        email=account.get("email"),  # 사용자가 동의하지 않으면 None
    )


# provider별 프로필 조회 함수 등록 (구글·애플은 나중에 추가)
PROFILE_FETCHERS = {
    SocialAccount.Provider.KAKAO: get_kakao_profile,
}


def generate_temp_nickname() -> str:
    while True:
        nickname = f"{TEMP_NICKNAME_PREFIX}{uuid.uuid4().hex[:8]}"
        if not User.objects.filter(nickname=nickname).exists():
            return nickname

@transaction.atomic
def get_or_create_social_user(provider, profile):
    social = (
        SocialAccount.objects.select_related("user")
        .filter(provider=provider, provider_uid=profile.provider_uid)
        .first()
    )
    if social:
        if profile.email and social.email != profile.email:
            social.email = profile.email
            social.save(update_fields=["email"])
        return social.user, False

    user = User(nickname=generate_temp_nickname(), profile_image=profile.profile_image)
    user.set_unusable_password()
    user.save()
    SocialAccount.objects.create(
        user=user, provider=provider,
        provider_uid=profile.provider_uid, email=profile.email,
    )
    return user, True