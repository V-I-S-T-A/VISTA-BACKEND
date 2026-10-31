import re
import secrets
import string

import cloudinary.uploader
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db import transaction
from .models import User


class VerifyOrganizationJoiningSerializer(serializers.Serializer):
    org_id = serializers.UUIDField()
    expected_joined_at = serializers.DateTimeField(allow_null=True, required=True)
    joined_at = serializers.DateTimeField()
    evidence = serializers.CharField(max_length=2000, allow_blank=False)

    def validate_joined_at(self, value):
        raw = self.initial_data.get("joined_at")
        parsed = parse_datetime(raw) if isinstance(raw, str) else None
        if parsed is None or timezone.is_naive(parsed):
            raise serializers.ValidationError("Include an explicit timezone offset or Z.")
        if value > timezone.now():
            raise serializers.ValidationError("Joining time cannot be in the future.")
        return value


def generate_temp_password(length=12):
    """
    Cryptographically secure random password containing at least one
    lowercase, uppercase, digit, and symbol.
    """
    symbols = "!@#$%^&*"
    alphabet = string.ascii_letters + string.digits + symbols
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in pwd)
            and any(c.isupper() for c in pwd)
            and any(c.isdigit() for c in pwd)
            and any(c in symbols for c in pwd)
        ):
            return pwd


class UserSerializer(serializers.ModelSerializer):
    department = serializers.CharField(source='org_id.name', read_only=True)
    org_image_url = serializers.URLField(source='org_id.image_url', read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = [
            "user_id", "org_id", "first_name", "last_name", "email",
            "role", "image_url", "is_active", "last_login", "department", "org_image_url",
            "must_change_password", "created_at", "updated_at", "org_joined_at",
        ]
        read_only_fields = ["user_id", "must_change_password", "created_at", "updated_at", "org_joined_at"]


class ProfileSerializer(UserSerializer):
    """Personal details returned by the signed-in user's profile endpoint."""

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ["birth_date", "gender", "phone_number"]


class UserCreateSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES, required=True)
    # Write-only upload field. The stored image_url is derived from the
    # Cloudinary response and is never set directly by the client.
    image = serializers.ImageField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = User
        fields = [
            "user_id", "org_id", "first_name", "last_name", "email", "role",
            "image", "image_url",
        ]
        read_only_fields = ["user_id", "image_url"]

    def validate_role(self, value):
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated or request.user.role != "admin":
            raise serializers.ValidationError("Only an admin can create users and assign roles.")
        return value

    def create(self, validated_data):
        image = validated_data.pop("image", None)
        temp_password = generate_temp_password()

        user = User.objects.create_user(password=temp_password, membership_actor=self.context["request"].user, **validated_data)
        user.must_change_password = True
        user.save(update_fields=["must_change_password"])

        if image:
            # No width/height/crop transformation is passed, so Cloudinary
            # stores the image at its original uploaded size.
            upload_result = cloudinary.uploader.upload(image, folder="vista/users")
            user.image_url = upload_result["secure_url"]
            user.save(update_fields=["image_url"])

        # Held in memory only (never saved) so the view can email it once.
        user._temp_password = temp_password
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(required=False, allow_blank=True, max_length=40)
    image = serializers.ImageField(write_only=True, required=False, allow_null=True)
    remove_image = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "org_id", "role", "is_active", "image", "remove_image", "image_url", "birth_date", "gender", "phone_number"]
        read_only_fields = ["image_url"]

    def validate_phone_number(self, value):
        if not value:
            return ""
        if not re.fullmatch(r"[+0-9()\s-]+", value):
            raise serializers.ValidationError("Use a Philippine mobile number, e.g. +63 912-345-6789.")
        digits = re.sub(r"\D", "", value)
        if digits.startswith("63") and len(digits) == 12:
            digits = digits[2:]
        elif digits.startswith("0") and len(digits) == 11:
            digits = digits[1:]
        if not re.fullmatch(r"9[0-9]{9}", digits):
            raise serializers.ValidationError("Enter 10 mobile digits starting with 9, e.g. 912-345-6789.")
        return "+63" + digits

    def validate_org_id(self, value):
        request = self.context.get("request")
        if not request or request.user.role != "admin":
            if not self.instance or self.instance.org_id_id != (value.pk if value else None):
                raise serializers.ValidationError("Only an admin can change organization membership.")
        return value

    def validate_birth_date(self, value):
        if value and value > timezone.localdate():
            raise serializers.ValidationError("Birth date cannot be in the future.")
        return value

    def validate_role(self, value):
        request = self.context.get("request")
        if not request or request.user.role != "admin":
            raise serializers.ValidationError("Only an admin can change roles.")
        return value

    def validate_is_active(self, value):
        request = self.context.get("request")
        if not request or request.user.role != "admin":
            raise serializers.ValidationError("Only an admin can change active status.")
        return value

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = User.objects.select_for_update().get(pk=instance.pk)
        request = self.context.get("request")
        instance._membership_actor = request.user if request else None
        if "org_id" in validated_data and (not request or request.user.role != "admin"):
            proposed = validated_data["org_id"]
            if instance.org_id_id != (proposed.pk if proposed else None):
                raise serializers.ValidationError({"org_id": "The membership changed; reload your profile."})
        image = validated_data.pop("image", None)
        remove_image = validated_data.pop("remove_image", False)
        instance = super().update(instance, validated_data)
        if image:
            upload_result = cloudinary.uploader.upload(image, folder="vista/users")
            instance.image_url = upload_result["secure_url"]
            instance.save(update_fields=["image_url"])
        elif remove_image:
            instance.image_url = ""
            instance.save(update_fields=["image_url"])
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.must_change_password = False
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(email=attrs["email"], password=attrs["password"])
        if not user:
            raise serializers.ValidationError("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("This account is inactive.")
        attrs["user"] = user
        return attrs

    def get_tokens(self, user):
        refresh = RefreshToken.for_user(user)
        refresh["role"] = user.role
        refresh["email"] = user.email
        return {"refresh": str(refresh), "access": str(refresh.access_token)}


class ConfirmPasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    code = serializers.CharField(write_only=True, max_length=6)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value

    def validate_code(self, value):
        from .models import PasswordChangeCode
        user = self.context["request"].user
        record = (
            PasswordChangeCode.objects.filter(user=user, code=value)
            .order_by("-created_at")
            .first()
        )
        if not record or not record.is_valid():
            raise serializers.ValidationError("Invalid or expired verification code.")
        self._code_record = record
        return value

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.must_change_password = False
        user.save()
        self._code_record.is_used = True
        self._code_record.save(update_fields=["is_used"])
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(min_length=6, max_length=6)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        from .models import PasswordChangeCode

        user = User.objects.filter(email__iexact=attrs["email"], is_active=True).first()
        if not user:
            raise serializers.ValidationError("Invalid or expired verification code.")
        record = (
            PasswordChangeCode.objects.filter(user=user, code=attrs["code"])
            .order_by("-created_at")
            .first()
        )
        if not record or not record.is_valid():
            raise serializers.ValidationError("Invalid or expired verification code.")
        self._user = user
        self._code_record = record
        return attrs

    def save(self, **kwargs):
        self._user.set_password(self.validated_data["new_password"])
        self._user.must_change_password = False
        self._user.save(update_fields=["password", "must_change_password"])
        self._code_record.is_used = True
        self._code_record.save(update_fields=["is_used"])
        return self._user
