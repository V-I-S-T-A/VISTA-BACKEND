from rest_framework import serializers
from .models import ReviewLog


class ReviewLogSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source="changed_by.full_name", read_only=True)
    submission_title = serializers.CharField(source="submission_id.title", read_only=True)

    class Meta:
        model = ReviewLog
        fields = [
            "log_id", "submission_id", "submission_title", "changed_by", "changed_by_name",
            "remarks_text", "old_status", "new_status", "changed_at",
        ]
        read_only_fields = fields