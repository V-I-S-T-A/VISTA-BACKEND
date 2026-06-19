from rest_framework import serializers
from .models import Organization


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["org_id", "name", "acronym", "description", "is_active", "created_at"]
        read_only_fields = ["org_id", "created_at"]

    def validate_acronym(self, value):
        return value.strip().upper()


class OrganizationListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["org_id", "name", "acronym", "is_active"]