from datetime import datetime
from django.db.models import Count, Q
from django.db import transaction

from django.http import FileResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters

from .models import User, OrganizationMembershipAudit
from .serializers import (
    UserSerializer,
    ProfileSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    VerifyOrganizationJoiningSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    generate_temp_password,
)
from .permissions import IsAdmin, IsSelfOrAdmin, IsAdminOrStaff
from .filters import UserFilter
from .pdf_generator import generate_user_list_pdf
from vista.pagination import StandardResultsPagination

#Import Audit Log Utilities ---
from audit_logs.utility import log_create, log_update, log_delete, log_login, log_logout

#Change password code model
from .models import PasswordChangeCode
from .serializers import ConfirmPasswordChangeSerializer
from .emails import send_welcome_email, send_password_code_email
from vista.email_backend import EmailDeliveryError

import logging

logger = logging.getLogger(__name__)

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().select_related("org_id")
    lookup_field = "user_id"
    pagination_class = StandardResultsPagination
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = UserFilter
    search_fields = ["first_name", "last_name", "email"]
    ordering_fields = ["first_name", "last_name", "email", "role", "created_at"]
    ordering = ["-created_at", "-user_id"]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action in ("update", "partial_update"):
            return UserUpdateSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action in ("create", "destroy", "resend_invitation", "verify_organization_joining"):
            return [IsAuthenticated(), IsAdmin()]
        if self.action in ("update", "partial_update", "retrieve"):
            return [IsAuthenticated(), IsSelfOrAdmin()]
        if self.action in ("list", "export_list", "summary"):
            return [IsAuthenticated(), IsAdminOrStaff()]
        return [IsAuthenticated()]

    @action(detail=True, methods=["post"], url_path="verify-organization-joining")
    def verify_organization_joining(self, request, *args, **kwargs):
        """Administrator attests to documentary evidence for the CURRENT membership."""
        target = self.get_object()
        payload = VerifyOrganizationJoiningSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        with transaction.atomic():
            target = User.objects.select_for_update().get(pk=target.pk)
            if not target.org_id_id or target.org_id_id != data["org_id"]:
                return Response({"detail": "The current organization changed; reload the account."}, status=409)
            if target.org_joined_at != data["expected_joined_at"]:
                # An identical retry is safe, but an earlier membership period is never restored.
                verified = target.membership_audits.filter(
                    reason="verification", joined_at=data["joined_at"], evidence=data["evidence"],
                    actor=request.user, org_id_value=data["org_id"],
                ).first()
                latest = target.membership_audits.first()
                if not (target.org_joined_at == data["joined_at"] and verified and latest.pk == verified.pk):
                    return Response({"detail": "The membership period changed; reload and verify its latest joining date."}, status=409)
            if target.org_joined_at != data["joined_at"]:
                OrganizationMembershipAudit.objects.create(
                    user=target, actor=request.user, previous_org_id=target.org_id_id,
                    org_id_value=target.org_id_id, previous_joined_at=target.org_joined_at,
                    joined_at=data["joined_at"], reason="verification", evidence=data["evidence"],
                )
                # Deliberately bypass automatic assignment timestamps, inside the same lock/transaction.
                User.objects.filter(pk=target.pk).update(org_joined_at=data["joined_at"])
                target.org_joined_at = data["joined_at"]
        return Response(ProfileSerializer(target).data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        return Response(queryset.aggregate(
            total=Count("pk"),
            staff=Count("pk", filter=Q(role="staff")),
            students=Count("pk", filter=Q(role="student")),
            inactive=Count("pk", filter=Q(is_active=False)),
        ))

    def perform_destroy(self, instance):
        if instance.pk == self.request.user.pk:
            raise PermissionDenied("You cannot delete your own account.")
        email, role = instance.email, instance.role
        # Log first so the audit entry is written even if delete raises
        log_delete(
            user=self.request.user,
            table_name="tbl_Users",
            old_data={"email": email, "role": role},
        )
        instance.delete()

    # Override perform_create ---
    def perform_create(self, serializer):
        instance = serializer.save()
        self._created_instance = instance
        log_create(
            user=self.request.user,
            table_name="tbl_Users",
            new_data={"email": instance.email, "role": instance.role},
        )
        try:
            sent_count = send_welcome_email(instance, instance._temp_password)
            instance._welcome_email_sent = sent_count == 1
            if not instance._welcome_email_sent:
                logger.error("Welcome email was not sent for %s", instance.email)
        except Exception:
            instance._welcome_email_sent = False
            logger.exception("Welcome email failed for %s", instance.email)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        instance = getattr(self, "_created_instance", None)
        if instance is not None:
            response.data["welcome_email_sent"] = getattr(
                instance, "_welcome_email_sent", False
            )
        return response

    @action(detail=True, methods=["post"], url_path="resend-invitation")
    def resend_invitation(self, request, *args, **kwargs):
        target = self.get_object()
        try:
            with transaction.atomic():
                # Lock only the user table: the usual queryset joins a nullable organization.
                user = User.objects.select_for_update().get(pk=target.pk)
                if not user.is_active or user.last_login is not None or not user.must_change_password:
                    return Response(
                        {"detail": "Invitations can only be resent to active accounts that have not signed in and still require a temporary password."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                password = generate_temp_password()
                user.set_password(password)
                user.save(update_fields=["password"])
                try:
                    sent = send_welcome_email(user, password)
                except EmailDeliveryError:
                    # Our email backends sanitize these messages for logging.
                    raise
                except Exception as exc:
                    # Do not expose provider responses or credentials to the client.
                    raise EmailDeliveryError(
                        f"Invitation email failed ({type(exc).__name__}); check the email backend configuration."
                    ) from None
                if sent != 1:
                    raise EmailDeliveryError("Invitation email was not accepted.")
        except EmailDeliveryError as exc:
            logger.warning("Resend invitation failed for user %s: %s", target.pk, exc)
            return Response(
                {"code": "invitation_email_failed", "detail": "The invitation could not be sent. Ask your system administrator to check the email service and renew the Gmail authorization token if needed. The existing password has not changed. You can try again after the email service is restored."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Invitation accepted for sending with a new temporary password. Ask the user to check their inbox or spam folder and use the newest invitation."})

    #  Override perform_update ---
    def perform_update(self, serializer):
        instance = serializer.save()
        log_update(
            user=self.request.user,
            table_name="tbl_Users",
            old_data={}, 
            new_data={"email": instance.email}
        )

    # --- NEW: PDF export of the (filtered) user list ---------------------
    @action(detail=False, methods=["get"], url_path="export/list")
    def export_list(self, request):
        """
        GET /api/users/export/list/

        Streams back a branded PDF of the currently filtered user list.
        Respects the same filters as the standard list endpoint (role,
        is_active, org_id, search, ordering, created_after/before) via
        `filter_queryset`, so "export what I'm looking at" works without
        any extra params on the frontend beyond what's already applied.
        """
        queryset = self.filter_queryset(self.get_queryset())

        filters_parts = []
        for param in ("role", "is_active", "org_id"):
            val = request.query_params.get(param)
            if val:
                filters_parts.append(f"{param}={val}")
        search = request.query_params.get("search")
        if search:
            filters_parts.append(f"search={search}")
        filters_applied = ", ".join(filters_parts) if filters_parts else "None"

        buffer = generate_user_list_pdf(
            list(queryset),
            generated_by=request.user.get_full_name(),
            filters_applied=filters_applied,
        )
        filename = f"users_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        return FileResponse(buffer, as_attachment=True, filename=filename, content_type="application/pdf")


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        is_first_login = user.last_login is None
        tokens = serializer.get_tokens(user)
        
        # Log the login ---
        log_login(user)
        
        # Update last_login
        from django.utils import timezone
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        
        return Response(
            {
                "user": UserSerializer(user).data,
                "tokens": tokens,
                "is_first_login": is_first_login,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            
            # Log the logout ---
            log_logout(request.user)
            
        except TokenError:
            return Response({"detail": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Successfully logged out."}, status=status.HTTP_205_RESET_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        return Response(ProfileSerializer(request.user).data)

    def patch(self, request):
        serializer = UserUpdateSerializer(
            request.user, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        # Track self-edits ---
        log_update(
            user=request.user,
            table_name="tbl_Users",
            old_data={},
            new_data={"profile": "updated"}
        )
        
        return Response(ProfileSerializer(user).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        # Track password change ---
        log_update(
            user=request.user,
            table_name="tbl_Users",
            old_data={},
            new_data={"action": "password_changed"}
        )
        
        return Response({"detail": "Password updated successfully."}, status=status.HTTP_200_OK)

class RequestPasswordChangeCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        record = PasswordChangeCode.generate_for(user)

        try:
            send_password_code_email(user, record)
        except Exception:
            logger.exception("Password change code email failed for %s", user.email)
            return Response(
                {"detail": "We couldn't send the email. Check the mail server configuration and try again."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Verification code sent to your email."}, status=status.HTTP_200_OK)


class ConfirmPasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ConfirmPasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()

        log_update(
            user=request.user,
            table_name="tbl_Users",
            old_data={},
            new_data={"action": "password_changed_via_email_verification"},
        )
        return Response({"detail": "Password updated successfully."}, status=status.HTTP_200_OK)


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        user = User.objects.filter(email__iexact=email, is_active=True).first()

        # Keep the response identical whether an account exists, so this
        # endpoint cannot be used to enumerate VISTA accounts.
        if user:
            record = PasswordChangeCode.generate_for(user)
            try:
                self._send_reset_email(user, record)
            except Exception:
                logger.exception("Password reset email delivery failed")
        return Response(
            {"detail": "If an active account uses that email, a verification code has been sent."},
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _send_reset_email(user, record):
        send_password_code_email(user, record, reset=True)


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        log_update(
            user=user,
            table_name="tbl_Users",
            old_data={},
            new_data={"action": "password_reset_via_email_verification"},
        )
        return Response({"detail": "Password reset successfully."}, status=status.HTTP_200_OK)
