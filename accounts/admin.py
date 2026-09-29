# accounts/admin.py
from django.contrib import admin
from .models import User, SocialAccount

admin.site.register(User)
admin.site.register(SocialAccount)