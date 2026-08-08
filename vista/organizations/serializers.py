import cloudinary.uploader
from rest_framework import serializers
from .models import Organization


class OrganizationSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(write_only=True, required=False, allow_null=True)
    class Meta:
        model = Organization
        fields = ["org_id", "name", "acronym", "description",  "image", "image_url", "is_active", "created_at"]
        read_only_fields = ["org_id", "created_at"]

    def validate_acronym(self, value):
        return value.strip().upper()

    def validate(self, attrs):
        if self.instance is None and not attrs.get("image"):
            raise serializers.ValidationError({"image": "Organization photo is required."})
        return attrs
    def create(self, validated_data):
        image = validated_data.pop("image", None)
        organization = Organization.objects.create(**validated_data)
        if image:
            upload_result = cloudinary.uploader.upload(image, folder="vista/organizations")
            organization.image_url = upload_result["secure_url"]
            organization.save(update_fields=["image_url"])
        return organization

    def update(self, instance, validated_data):
        image = validated_data.pop("image", None)
        instance = super().update(instance, validated_data)
        if image:
            upload_result = cloudinary.uploader.upload(image, folder="vista/organizations")
            instance.image_url = upload_result["secure_url"]
            instance.save(update_fields=["image_url"])
        return instance


class OrganizationListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["org_id", "name", "acronym", "image_url", "is_active"]