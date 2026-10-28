from rest_framework import serializers
from .models import DriveArchive, GoogleDriveConnection


class DriveArchiveSerializer(serializers.ModelSerializer):
    archived_by_name = serializers.SerializerMethodField()

    def get_archived_by_name(self, obj):
        if not obj.archived_by:
            return None
        return obj.archived_by.get_full_name().strip() or None

    class Meta:
        model = DriveArchive
        fields = [
            "archive_id",
            "archived_by_name",
            "drive_file_id",
            "file_name",
            "drive_view_link",
            "root_folder_id",
            "root_folder_name",
            "target_folder_id",
            "folder_path",
            "upload_kind",
            "archived_at",
        ]
        read_only_fields = fields


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

class DriveUploadSerializer(serializers.Serializer):
    submission_id = serializers.UUIDField()
    file = serializers.FileField()
    file_name = serializers.CharField(required=False, allow_blank=True)
    folder_id = serializers.CharField(required=False, allow_blank=True)
    use_auto_folder = serializers.BooleanField(required=False, default=True)
    upload_kind = serializers.ChoiceField(
        choices=("approved", "report"), required=False, default="approved"
    )
