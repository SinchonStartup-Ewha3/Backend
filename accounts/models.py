# accounts/models.py
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models

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
    nickname = models.CharField(max_length=20, unique=True)
    profile_image = models.URLField(max_length=500, null=True, blank=True)
    character_type = models.PositiveSmallIntegerField(null=True, blank=True)
    location_mode = models.CharField(max_length=10, null=True, blank=True)  # GPS / MANUAL
    last_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    region = models.ForeignKey("core.Region", null=True, blank=True, on_delete=models.SET_NULL)
    is_onboarded = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()
    USERNAME_FIELD = "nickname"

class SocialAccount(models.Model):
    class Provider(models.TextChoices):
        KAKAO = "KAKAO", "카카오"
        GOOGLE = "GOOGLE", "구글"
        APPLE = "APPLE", "애플"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="social_accounts")
    provider = models.CharField(max_length=20, choices=Provider.choices)
    provider_uid = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_uid"],
                name="uniq_social_provider_uid",
            )
        ]