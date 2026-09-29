from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import SocialLoginView

urlpatterns = [
    path("social-login/", SocialLoginView.as_view(), name="social-login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
]