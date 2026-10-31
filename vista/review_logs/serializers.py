from rest_framework import serializers
from .models import ReviewLog, ReviewReply, REPLY_MAX_LENGTH
from submissions.visibility import can_reply_to_submission


class ReviewLogSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source="changed_by.full_name", read_only=True)
    changed_by_image_url = serializers.URLField(
        source="changed_by.image_url",
        read_only=True,
        allow_null=True,
    )
    submission_title = serializers.CharField(source="submission_id.title", read_only=True)
    reply_count = serializers.IntegerField(read_only=True)
    can_reply = serializers.SerializerMethodField()

    def get_can_reply(self, obj):
        # Existing review remarks are staff-managed. Keep their threads available
        # if the original reviewer later leaves or their account is removed.
        return bool(obj.remarks_text.strip()
                    and can_reply_to_submission(self.context["request"].user, obj.submission_id))

    class Meta:
        model = ReviewLog
        fields = [
            "log_id", "submission_id", "submission_title", "changed_by", "changed_by_name",
            "changed_by_image_url", "remarks_text", "attachment_change", "old_status", "new_status", "changed_at",
            "reply_count", "can_reply",
        ]
        read_only_fields = fields


class ReviewReplySerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.full_name", read_only=True, default="Former user")
    author_role = serializers.CharField(source="author.role", read_only=True, default="")
    author_image_url = serializers.URLField(source="author.image_url", read_only=True, allow_null=True, default=None)
    reply_to_name = serializers.SerializerMethodField()

    def get_reply_to_name(self, obj):
        author = obj.parent_reply.author if obj.parent_reply_id else obj.review_log.changed_by
        return author.full_name if author else "Former user"

    class Meta:
        model = ReviewReply
        fields = ["reply_id", "review_log", "parent_reply", "author", "author_name", "author_role",
                  "author_image_url", "reply_to_name", "message", "created_at", "client_request_id"]
        read_only_fields = fields


class ReviewReplyCreateSerializer(serializers.Serializer):
    parent_reply = serializers.UUIDField(required=False, allow_null=True)
    message = serializers.CharField(max_length=REPLY_MAX_LENGTH, allow_blank=False, trim_whitespace=True)
    client_request_id = serializers.UUIDField(required=True)

    def validate_parent_reply(self, value):
        if value and not ReviewReply.objects.filter(pk=value, review_log=self.context["review_log"]).exists():
            raise serializers.ValidationError("The reply target must belong to this history entry.")
        return value
