# accounts/models.py
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models

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

    USERNAME_FIELD = "nickname"
    objects = ...  # BaseUserManager 구현