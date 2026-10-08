# accounts/models.py
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
import re

TEMP_NICKNAME_PREFIX = "user_"
TEMP_NICKNAME_PATTERN = re.compile(r"^user_[0-9a-f]{8}$")


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, nickname, password=None, **extra_fields):
        if not nickname:
            raise ValueError("닉네임은 필수입니다.")
        user = self.model(nickname=nickname, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()  # 소셜 로그인 유저는 비밀번호 없음
        user.save(using=self._db)
        return user

    def create_superuser(self, nickname, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_onboarded", True)

        if not extra_fields.get("is_staff") or not extra_fields.get("is_superuser"):
            raise ValueError("superuser는 is_staff와 is_superuser가 True여야 합니다.")
        return self.create_user(nickname, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    class LocationMode(models.TextChoices):
        GPS = "GPS", "현재 위치"
        MANUAL = "MANUAL", "직접 설정"

    nickname = models.CharField(max_length=20, unique=True)
    profile_image = models.URLField(max_length=500, null=True, blank=True)
    location_mode = models.CharField(
        max_length=10, choices=LocationMode.choices, null=True, blank=True
    )
    last_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    region = models.ForeignKey("core.Region", null=True, blank=True, on_delete=models.SET_NULL)
    is_onboarded = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()
    USERNAME_FIELD = "nickname"

    @property
    def has_temp_nickname(self) -> bool:
        return bool(TEMP_NICKNAME_PATTERN.match(self.nickname))

    def refresh_onboarding_status(self):
        """닉네임과 위치가 모두 설정되면 온보딩 완료"""
        if not self.is_onboarded and self.region_id and not self.has_temp_nickname:
            self.is_onboarded = True

class SocialAccount(models.Model):
    class Provider(models.TextChoices):
        KAKAO = "KAKAO", "카카오"
        GOOGLE = "GOOGLE", "구글"
        APPLE = "APPLE", "애플"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="social_accounts")
    provider = models.CharField(max_length=20, choices=Provider.choices)
    provider_uid = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    email = models.EmailField(null=True, blank=True)  # 프로필 ID 표시용

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_uid"],
                name="uniq_social_provider_uid",
            )
        ]