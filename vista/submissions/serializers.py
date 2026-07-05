from rest_framework import serializers
from .models import Submission


class SubmissionSerializer(serializers.ModelSerializer):
    submitted_by_name = serializers.CharField(source="submitted_by.full_name", read_only=True)
    org_name = serializers.CharField(source="org_id.name", read_only=True)
    category_name = serializers.CharField(source="category_id.name", read_only=True)
    doc_type_name = serializers.CharField(source="doc_type_id.name", read_only=True)
    academic_year = serializers.CharField(source="academic_year_id.year", read_only=True)

    class Meta:
        model = Submission
        fields = [
            "submission_id",
            "doc_type_id",
            "doc_type_name",
            "submitted_by",
            "submitted_by_name",
            "org_id",
            "org_name",
            "category_id",
            "category_name",
            "academic_year_id",
            "academic_year",
            "title",
            "description",
            "status",
            "submitted_at",
            "updated_at",
        ]
        read_only_fields = ["submission_id", "submitted_by", "status", "submitted_at", "updated_at"]


class SubmissionListSerializer(serializers.ModelSerializer):
    submitted_by_name = serializers.CharField(source="submitted_by.full_name", read_only=True)
    org_name = serializers.CharField(source="org_id.name", read_only=True)
    category_name = serializers.CharField(source="category_id.name", read_only=True)

    class Meta:
        model = Submission
        fields = [
            "submission_id",
            "title",
            "status",
            "submitted_by_name",
            "org_name",
            "category_name",
            "submitted_at",
        ]


class SubmissionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Submission
        fields = [
            "submission_id",
            "doc_type_id",
            "org_id",
            "category_id",
            "academic_year_id",
            "title",
            "description",
        ]
        read_only_fields = ["submission_id"]

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["submitted_by"] = request.user
        validated_data["status"] = Submission.STATUS_PENDING
        return Submission.objects.create(**validated_data)


class SubmissionStatusUpdateSerializer(serializers.ModelSerializer):
    remarks_text = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Submission
        fields = ["status", "remarks_text"]

    def validate_status(self, value):
        current = self.instance.status
        valid_transitions = {
            Submission.STATUS_PENDING: [Submission.STATUS_UNDER_REVIEW, Submission.STATUS_REJECTED],
            Submission.STATUS_UNDER_REVIEW: [
                Submission.STATUS_APPROVED,
                Submission.STATUS_REJECTED,
                Submission.STATUS_RESUBMISSION_REQUIRED,
            ],
            Submission.STATUS_RESUBMISSION_REQUIRED: [Submission.STATUS_UNDER_REVIEW, Submission.STATUS_PENDING],
            Submission.STATUS_APPROVED: [],
            Submission.STATUS_REJECTED: [],
        }
        if value == current:
            raise serializers.ValidationError("Submission is already in this status.")
        if value not in valid_transitions.get(current, []):
            raise serializers.ValidationError(
                f"Cannot transition from '{current}' to '{value}'."
            )
        return value

    def update(self, instance, validated_data):
        from review_logs.models import ReviewLog

        request = self.context["request"]
        remarks_text = validated_data.pop("remarks_text", "")
        old_status = instance.status
        new_status = validated_data["status"]

        instance.status = new_status
        instance.save(update_fields=["status", "updated_at"])

        ReviewLog.objects.create(
            submission_id=instance,
            changed_by=request.user,
            remarks_text=remarks_text,
            old_status=old_status,
            new_status=new_status,
        )

        if new_status == Submission.STATUS_APPROVED:
            from integrations.tasks import sync_submission_to_drive

            sync_submission_to_drive.delay(
                submission_id=str(instance.submission_id),
                staff_user_id=str(request.user.user_id),
            )

        return instance