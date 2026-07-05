from rest_framework import serializers
from .models import GoogleDriveConnection


class GoogleDriveConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoogleDriveConnection
        fields = [
            "connection_id",
            "google_account_email",
            "folder_mode",
            "folder_id",
            "folder_name",
            "is_active",
            "last_synced_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class FolderSelectSerializer(serializers.Serializer):
    folder_id = serializers.CharField()
    folder_name = serializers.CharField()


class FolderCreateSerializer(serializers.Serializer):
    folder_name = serializers.CharField(max_length=255)