import cloudinary.uploader
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from .models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "user_id", "org_id", "first_name", "last_name", "email",
            "role", "image_url", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["user_id", "created_at", "updated_at"]


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES, required=True)
    # Write-only upload field. The stored image_url is derived from the
    # Cloudinary response and is never set directly by the client.
    image = serializers.ImageField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = User
        fields = [
            "user_id", "org_id", "first_name", "last_name", "email", "role",
            "password", "password_confirm", "image", "image_url",
        ]
        read_only_fields = ["user_id", "image_url"]

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def validate_role(self, value):
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated or request.user.role != "admin":
            raise serializers.ValidationError("Only an admin can create users and assign roles.")
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        image = validated_data.pop("image", None)
        user = User.objects.create_user(password=password, **validated_data)
        if image:
            # No width/height/crop transformation is passed, so Cloudinary
            # stores the image at its original uploaded size.
            upload_result = cloudinary.uploader.upload(image, folder="vista/users")
            user.image_url = upload_result["secure_url"]
            user.save(update_fields=["image_url"])
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "org_id", "role", "is_active", "image", "image_url"]
        read_only_fields = ["image_url"]

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

    def update(self, instance, validated_data):
        image = validated_data.pop("image", None)
        instance = super().update(instance, validated_data)
        if image:
            upload_result = cloudinary.uploader.upload(image, folder="vista/users")
            instance.image_url = upload_result["secure_url"]
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