from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import UserViewSet, LoginView, LogoutView, MeView, ChangePasswordView, RequestPasswordChangeCodeView, ConfirmPasswordChangeView, PasswordResetRequestView, PasswordResetConfirmView

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("auth/change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
    path("auth/change-password/request-code/", RequestPasswordChangeCodeView.as_view(), name="auth-change-password-request-code"),
    path("auth/change-password/confirm/", ConfirmPasswordChangeView.as_view(), name="auth-change-password-confirm"),
    path("auth/password-reset/request/", PasswordResetRequestView.as_view(), name="auth-password-reset-request"),
    path("auth/password-reset/confirm/", PasswordResetConfirmView.as_view(), name="auth-password-reset-confirm"),
    path("", include(router.urls)),
]
