from rest_framework import serializers
from users.models import User
from .models import Submission
from documents.models import Document
from documents.serializers import DocumentSerializer # Ensure you import this!

class SubmissionSerializer(serializers.ModelSerializer):
    submitted_by_name = serializers.CharField(source="submitted_by.get_full_name", read_only=True)
    submitted_by_email = serializers.CharField(source="submitted_by.email", read_only=True)
    org_name = serializers.CharField(source="org_id.name", read_only=True)
    org_image_url = serializers.CharField(source="org_id.image_url", read_only=True, allow_null=True)
    category_name = serializers.CharField(source="category_id.name", read_only=True)
    doc_type_name = serializers.CharField(source="doc_type_id.name", read_only=True)
    academic_year = serializers.CharField(source="academic_year_id.year", read_only=True)
    documents = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = [
            "submission_id",
            "doc_type_id",
            "doc_type_name",
            "submitted_by",
            "submitted_by_name",
            "submitted_by_email",
            "org_id",
            "org_name",
            "org_image_url",
            "category_id",
            "category_name",
            "academic_year_id",
            "academic_year",
            "title",
            "description",
            "status",
            "submitted_at",
            "updated_at",
            "documents", # NEW: Expose the documents array
        ]
        read_only_fields = ["submission_id", "submitted_by", "status", "submitted_at", "updated_at"]

    # NEW: Define the function that grabs the documents
    def get_documents(self, obj):
        # Fetch all documents where submission_id matches this submission, and it is the current version
        docs = Document.objects.filter(submission_id=obj, is_current=True)
        return DocumentSerializer(docs, many=True).data


class SubmissionListSerializer(serializers.ModelSerializer):
    submitted_by_name = serializers.CharField(source="submitted_by.get_full_name", read_only=True)
    submitted_by_email = serializers.CharField(source="submitted_by.email", read_only=True)
    org_name = serializers.CharField(source="org_id.name", read_only=True)
    org_image_url = serializers.CharField(source="org_id.image_url", read_only=True, allow_null=True)
    category_name = serializers.CharField(source="category_id.name", read_only=True)
    doc_type_name = serializers.CharField(source="doc_type_id.name", read_only=True)

    class Meta:
        model = Submission
        fields = [
            "submission_id",
            "title",
            "status",
            "submitted_by_name",
            "submitted_by_email",
            "org_name",
            "org_image_url",
            "category_name",
            "doc_type_name",
            "submitted_at",
        ]


class SubmissionCreateSerializer(serializers.ModelSerializer):
    submitted_by = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Submission
        fields = [
            "submission_id",
            "doc_type_id",
            "org_id",
            "category_id",
            "academic_year_id",
            "submitted_by",
            "title",
            "description",
        ]
        read_only_fields = ["submission_id"]

    def validate(self, data):
        request = self.context["request"]
        submitted_by = data.get("submitted_by")
        org_id = data.get("org_id")

        if submitted_by:
            if request.user.role not in ("staff", "admin"):
                raise serializers.ValidationError(
                    {"submitted_by": "Only staff or admin users may set the submitter."}
                )
            if org_id and submitted_by.org_id_id != org_id.org_id:
                raise serializers.ValidationError(
                    {
                        "submitted_by": 
                        "Selected submitter must belong to the selected organization.",
                    }
                )

        return data

    def create(self, validated_data):
        request = self.context["request"]
        if not validated_data.get("submitted_by") or request.user.role not in ("staff", "admin"):
            validated_data["submitted_by"] = request.user
        validated_data["status"] = Submission.STATUS_PENDING
        return Submission.objects.create(**validated_data)


class SubmissionStatusUpdateSerializer(serializers.ModelSerializer):
    remarks_text = serializers.CharField(write_only=True, required=False, allow_blank=True)
    file = serializers.FileField(write_only=True, required=False, allow_null=True)
    drive_folder_id = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Submission
        fields = ["status", "remarks_text", "file", "drive_folder_id"]

    def validate_status(self, value):
        current = self.instance.status
        valid_transitions = {
            Submission.STATUS_PENDING: [
                Submission.STATUS_UNDER_REVIEW,
                Submission.STATUS_APPROVED,
                Submission.STATUS_REJECTED,
                Submission.STATUS_RESUBMISSION_REQUIRED,
            ],
            Submission.STATUS_UNDER_REVIEW: [
                Submission.STATUS_APPROVED,
                Submission.STATUS_REJECTED,
                Submission.STATUS_RESUBMISSION_REQUIRED,
            ],
            Submission.STATUS_RESUBMISSION_REQUIRED: [
                Submission.STATUS_UNDER_REVIEW,
                Submission.STATUS_PENDING,
                Submission.STATUS_APPROVED,
                Submission.STATUS_REJECTED,
            ],
            Submission.STATUS_APPROVED: [
                Submission.STATUS_UNDER_REVIEW,
                Submission.STATUS_RESUBMISSION_REQUIRED,
                Submission.STATUS_REJECTED,
            ],
            Submission.STATUS_REJECTED: [
                Submission.STATUS_UNDER_REVIEW,
                Submission.STATUS_RESUBMISSION_REQUIRED,
                Submission.STATUS_APPROVED,
            ],
        }
        if value == current:
            # Allow keeping current status if attaching a replacement file or re-confirming Drive upload
            if not self.initial_data.get("file") and not self.initial_data.get("drive_folder_id"):
                raise serializers.ValidationError("Submission is already in this status.")
        elif value not in valid_transitions.get(current, []):
            raise serializers.ValidationError(
                f"Cannot transition from '{current}' to '{value}'."
            )
        return value

    def update(self, instance, validated_data):
        from review_logs.models import ReviewLog
        from documents.models import Document
        import cloudinary.uploader
        import logging
        from django.utils import timezone
        logger = logging.getLogger(__name__)

        request = self.context["request"]
        remarks_text = validated_data.pop("remarks_text", "")
        replacement_file = validated_data.pop("file", None)
        drive_folder_id = validated_data.pop("drive_folder_id", None)
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

        final_file_bytes = None
        final_file_name = None
        final_mime_type = "application/pdf"

        # If a replacement final PDF was uploaded:
        if replacement_file:
            try:
                final_file_bytes = replacement_file.read()
                final_file_name = replacement_file.name
                final_mime_type = getattr(replacement_file, "content_type", None) or "application/pdf"
                file_size_kb = max(1, len(final_file_bytes) // 1024)

                # Reset read pointer for Cloudinary uploader
                replacement_file.seek(0)
                upload_result = cloudinary.uploader.upload(
                    replacement_file,
                    folder="vista/documents",
                    resource_type="auto",
                )
                secure_url = upload_result.get("secure_url") or upload_result.get("url")

                # Remove old document(s) for this submission in the system
                Document.objects.filter(submission_id=instance).delete()

                # Create the new current document record in the system
                Document.objects.create(
                    submission_id=instance,
                    file_name=final_file_name,
                    file_url=secure_url,
                    mime_type=final_mime_type,
                    file_size_kb=file_size_kb,
                    version=1,
                    is_current=True,
                )
            except Exception as e:
                logger.error("Failed to upload replacement document to Cloudinary: %s", e)

        # Automated Google Drive Sync upon Approval / Verification:
        if new_status == Submission.STATUS_APPROVED:
            connection = getattr(request.user, "drive_connection", None)
            if connection and connection.is_active:
                try:
                    from integrations import google_client
                    # Always use Akane's automated subfolder hierarchy under the root folder configured on GDrive sync:
                    # Root (connection.folder_id) -> Academic Year -> Organization -> Document Type
                    folder_dict, path_segments = google_client.resolve_submission_folder_path(connection, instance)
                    target_folder_id = folder_dict["id"]
                    logger.info("Archiving submission to automated Drive subfolder path %s (ID: %s)", path_segments, target_folder_id)

                    # If replacement file bytes are available in memory, upload directly
                    if final_file_bytes and final_file_name:
                        google_client.upload_file_to_folder(
                            connection=connection,
                            folder_id=target_folder_id,
                            file_name=final_file_name,
                            file_bytes=final_file_bytes,
                            mime_type=final_mime_type,
                        )
                        connection.last_synced_at = timezone.now()
                        connection.save(update_fields=["last_synced_at"])
                    else:
                        # Otherwise fetch the existing current document and upload
                        docs = Document.objects.filter(submission_id=instance, is_current=True)
                        if docs.exists():
                            import requests
                            for doc in docs:
                                try:
                                    res = requests.get(doc.file_url, timeout=30)
                                    if res.ok:
                                        google_client.upload_file_to_folder(
                                            connection=connection,
                                            folder_id=target_folder_id,
                                            file_name=doc.file_name,
                                            file_bytes=res.content,
                                            mime_type=doc.mime_type,
                                        )
                                        connection.last_synced_at = timezone.now()
                                        connection.save(update_fields=["last_synced_at"])
                                except Exception as sync_err:
                                    logger.warning("Error uploading doc %s to Drive: %s", doc.document_id, sync_err)
                except Exception as drive_err:
                    logger.warning("Google Drive sync failed: %s", drive_err)

        return instance