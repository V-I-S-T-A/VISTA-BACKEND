from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters

from .models import User
from .serializers import (
    UserSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
)
from .permissions import IsAdmin, IsSelfOrAdmin
from .filters import UserFilter
from vista.pagination import StandardResultsPagination

#Import Audit Log Utilities ---
from audit_logs.utility import log_create, log_update, log_delete, log_login, log_logout


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().select_related("org_id")
    lookup_field = "user_id"
    pagination_class = StandardResultsPagination
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = UserFilter
    search_fields = ["first_name", "last_name", "email"]
    ordering_fields = ["first_name", "last_name", "email", "role", "created_at"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action in ("update", "partial_update"):
            return UserUpdateSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), IsAdmin()]
        if self.action in ("update", "partial_update", "retrieve"):
            return [IsAuthenticated(), IsSelfOrAdmin()]
        if self.action in ("destroy", "list"):
            return [IsAuthenticated(), IsAdmin()]
        return [IsAuthenticated()]

    # Override perform_create ---
    def perform_create(self, serializer):
        instance = serializer.save()
        log_create(
            user=self.request.user,
            table_name="tbl_Users",
            new_data={"email": instance.email, "role": instance.role}
        )

    #  Override perform_update ---
    def perform_update(self, serializer):
        instance = serializer.save()
        log_update(
            user=self.request.user,
            table_name="tbl_Users",
            old_data={}, 
            new_data={"email": instance.email}
        )

    #  Add tracking to perform_destroy ---
    def perform_destroy(self, instance):
        email = instance.email
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        log_delete(
            user=self.request.user,
            table_name="tbl_Users",
            old_data={"email": email}
        )


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        tokens = serializer.get_tokens(user)
        
        # Log the login ---
        log_login(user)
        
        return Response(
            {
                "user": UserSerializer(user).data,
                "tokens": tokens,
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
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserUpdateSerializer(
            request.user, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        # Track self-edits ---
        log_update(
            user=request.user,
            table_name="tbl_Users",
            old_data={},
            new_data={"profile": "updated"}
        )
        
        return Response(UserSerializer(request.user).data)


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