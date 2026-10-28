from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    submission_title = serializers.CharField(source="submission_id.title", read_only=True)
    submission_status = serializers.CharField(source="submission_id.status", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "notification_id", "submission_id", "submission_title",
            "submission_status", "type", "message", "is_read", "created_at",
        ]
        read_only_fields = fields
