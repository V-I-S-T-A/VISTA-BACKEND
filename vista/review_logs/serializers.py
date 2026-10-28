from rest_framework import serializers
from .models import ReviewLog


class ReviewLogSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source="changed_by.full_name", read_only=True)
    changed_by_image_url = serializers.URLField(
        source="changed_by.image_url",
        read_only=True,
        allow_null=True,
    )
    submission_title = serializers.CharField(source="submission_id.title", read_only=True)

    class Meta:
        model = ReviewLog
        fields = [
            "log_id", "submission_id", "submission_title", "changed_by", "changed_by_name",
            "changed_by_image_url", "remarks_text", "attachment_change", "old_status", "new_status", "changed_at",
        ]
        read_only_fields = fields
