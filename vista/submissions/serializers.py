from rest_framework import serializers
from users.models import User
from .models import Submission
from documents.models import Document
from documents.serializers import DocumentSerializer # Ensure you import this!
from .emails import send_priority_change_email, send_status_change_email
from notifications.models import Notification
import logging
from typing import NamedTuple
from urllib.parse import urlparse

import cloudinary.uploader
import requests
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

logger = logging.getLogger(__name__)

MAX_FILES_PER_UPDATE = 10
MAX_FILE_SIZE_MB = 25

class FilePayload(NamedTuple):
    """A file held in memory, ready to be sent to Drive."""
    name: str
    content: bytes
    mime_type: str

class SubmissionSerializer(serializers.ModelSerializer):
    submitted_by_name = serializers.CharField(source="submitted_by.get_full_name", read_only=True)
    submitted_by_email = serializers.CharField(source="submitted_by.email", read_only=True)
    org_name = serializers.CharField(source="org_id.name", read_only=True)
    org_image_url = serializers.CharField(source="org_id.image_url", read_only=True, allow_null=True)
    category_name = serializers.CharField(source="category_id.name", read_only=True)
    doc_type_name = serializers.CharField(source="doc_type_id.name", read_only=True)
    academic_year = serializers.CharField(source="academic_year_id.year", read_only=True)
    documents = serializers.SerializerMethodField()
    drive_archives = serializers.SerializerMethodField()
    is_accomplishment_report = serializers.BooleanField(read_only=True)

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
            "priority_escalation",
            "submitted_at",
            "updated_at",
            "documents",
            "drive_archives",
            "is_accomplishment_report",
        ]
        read_only_fields = ["submission_id", "submitted_by", "status", "priority_escalation", "submitted_at", "updated_at", "is_accomplishment_report"]

    # NEW: Define the function that grabs the documents
    def get_documents(self, obj):
        request = self.context.get("request")
        if request and getattr(request.user, "role", None) == "student":
            return []
        # Returned entries keep their document rows for history, but those
        # files must never be exposed as active attachments. This also hides
        # legacy rows that were left current before the rejection transition
        # began deactivating them.
        if obj.status == Submission.STATUS_REJECTED:
            return []
        # Fetch all documents where submission_id matches this submission, and it is the current version
        docs = Document.objects.filter(submission_id=obj, is_current=True)
        return DocumentSerializer(docs, many=True).data

    def get_drive_archives(self, obj):
        request = self.context.get("request")
        if request and getattr(request.user, "role", None) == "student":
            return []

        from integrations.serializers import DriveArchiveSerializer

        archives = obj.drive_archives.all()
        return DriveArchiveSerializer(archives, many=True).data


class SubmissionListSerializer(serializers.ModelSerializer):
    submitted_by_name = serializers.CharField(source="submitted_by.get_full_name", read_only=True)
    submitted_by_email = serializers.CharField(source="submitted_by.email", read_only=True)
    org_name = serializers.CharField(source="org_id.name", read_only=True)
    org_image_url = serializers.CharField(source="org_id.image_url", read_only=True, allow_null=True)
    category_name = serializers.CharField(source="category_id.name", read_only=True)
    doc_type_name = serializers.CharField(source="doc_type_id.name", read_only=True)
    academic_year = serializers.CharField(source="academic_year_id.year", read_only=True)
    is_accomplishment_report = serializers.BooleanField(read_only=True)

    class Meta:
        model = Submission
        fields = [
            "submission_id",
            "title",
            "status",
            "priority_escalation",
            "academic_year",
            "submitted_by_name",
            "submitted_by_email",
            "org_name",
            "org_image_url",
            "category_name",
            "doc_type_name",
            "submitted_at",
            "is_accomplishment_report",
        ]


class SubmissionCreateSerializer(serializers.ModelSerializer):
    description = serializers.CharField(required=False, allow_blank=True, default="")
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
    attachment_action = serializers.ChoiceField(
        choices=("add", "replace"), write_only=True, required=False,
    )
    attachment = serializers.JSONField(write_only=True, required=False)
    files = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False,
        max_length=MAX_FILES_PER_UPDATE,
    )
    report_files = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False,
        max_length=MAX_FILES_PER_UPDATE,
    )
    drive_folder_id = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Submission
        fields = ["status", "priority_escalation", "remarks_text", "files", "report_files", "drive_folder_id", "attachment_action", "attachment"]

    def validate(self, attrs):
        attachment_action = attrs.get("attachment_action")
        attachment = attrs.get("attachment")
        if bool(attachment_action) != bool(attachment):
            raise serializers.ValidationError({"attachment": "Choose an attachment and whether to add or replace it."})
        if attachment:
            if not isinstance(attachment, dict):
                raise serializers.ValidationError({"attachment": "Attachment details must be an object."})
            if attrs.get("status") != Submission.STATUS_UNDER_REVIEW:
                raise serializers.ValidationError({"attachment": "Attachments can only be changed while moving a submission to On Process."})
            for required in ("file_name", "file_url", "mime_type", "file_size_kb"):
                if required not in attachment:
                    raise serializers.ValidationError({"attachment": f"The {required} field is required."})
            for required in ("cloudinary_public_id", "cloudinary_resource_type"):
                if not attachment.get(required):
                    raise serializers.ValidationError({"attachment": f"The {required} field is required."})
            if attachment["cloudinary_resource_type"] not in ("image", "video", "raw"):
                raise serializers.ValidationError({"attachment": "The Cloudinary resource type is invalid."})
            if len(str(attachment["cloudinary_public_id"])) > 255:
                raise serializers.ValidationError({"attachment": "The Cloudinary asset identity is invalid."})
            parsed_url = urlparse(str(attachment["file_url"]))
            if parsed_url.scheme != "https" or parsed_url.hostname != "res.cloudinary.com":
                raise serializers.ValidationError({"attachment": "The attachment must be stored in Cloudinary."})
            if not isinstance(attachment["file_size_kb"], int) or attachment["file_size_kb"] < 0:
                raise serializers.ValidationError({"attachment": "File size must be a non-negative number of KB."})
        is_verifying = attrs.get("status") == Submission.STATUS_APPROVED
        if attrs.get("files") and self.instance.is_accomplishment_report and not is_verifying:
            raise serializers.ValidationError(
                {"files": "An approved document can only be attached when verifying an Accomplishment Report."}
            )
        if attrs.get("report_files") and not self.instance.is_accomplishment_report:
            raise serializers.ValidationError(
                {"report_files": "Report files can only be attached to an Accomplishment Report."}
            )
        return attrs

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
            # The web review flow updates status separately from its async Drive uploads.
            return value
        elif value not in valid_transitions.get(current, []):
            raise serializers.ValidationError(
                f"Cannot transition from '{current}' to '{value}'."
            )
        return value
    
    def validate_files(self, files):
        return self._validate_file_sizes(files)

    def validate_report_files(self, files):
        return self._validate_file_sizes(files)

    @staticmethod
    def _validate_file_sizes(files):
        limit = MAX_FILE_SIZE_MB * 1024 * 1024
        for f in files:
            if f.size > limit:
                raise serializers.ValidationError(f"'{f.name}' exceeds the {MAX_FILE_SIZE_MB} MB limit.")
        return files

    def update(self, instance, validated_data):
        from review_logs.models import ReviewLog  # local import avoids a circular import

        request = self.context["request"]
        remarks_text = validated_data.pop("remarks_text", "")
        uploaded_files = validated_data.pop("files", [])
        report_files = validated_data.pop("report_files", [])
        attachment_action = validated_data.pop("attachment_action", None)
        attachment = validated_data.pop("attachment", None)
        drive_folder_id = self.initial_data.get("drive_folder_id", "")
        validated_data.pop("drive_folder_id", None)  # The selected folder is used as the archive root.
        old_status, new_status = instance.status, validated_data.get("status", instance.status)
        old_priority_escalation = instance.priority_escalation
        priority_was_added = False

        payloads = [self._to_payload(f) for f in uploaded_files]
        report_payloads = [self._to_payload(f) for f in report_files]
        # For an Accomplishment Report the upload is the *approved document*, a separate
        # piece of the package, so it must not replace the report stored in the system.
        replaces_documents = bool(payloads) and not instance.is_accomplishment_report
        # External uploads come first, so a failure leaves the database untouched.
        urls = self._upload_to_cloudinary(uploaded_files) if replaces_documents else []

        with transaction.atomic():
            active_file_names = list(
                Document.objects.filter(submission_id=instance, is_current=True)
                .order_by("uploaded_at")
                .values_list("file_name", flat=True)
            )
            attachment_change = {}
            update_fields = ["updated_at"]
            if "status" in validated_data:
                instance.status = new_status
                update_fields.append("status")
            if "priority_escalation" in validated_data:
                instance.priority_escalation = validated_data["priority_escalation"]
                update_fields.append("priority_escalation")
                priority_was_added = instance.priority_escalation and not old_priority_escalation
            instance.save(update_fields=update_fields)
            if replaces_documents:
                attachment_change = {
                    "action": "replaced",
                    "previous_files": active_file_names,
                    "new_files": [payload.name for payload in payloads],
                }
                self._replace_documents(instance, payloads, urls)
            if attachment:
                attachment_change = {
                    "action": "added" if attachment_action == "add" else "replaced",
                    "previous_files": active_file_names if attachment_action == "replace" else [],
                    "new_files": [attachment["file_name"]],
                }
                self._save_attachment(instance, attachment_action, attachment)
            if new_status == Submission.STATUS_REJECTED:
                # Retain the historical records, but detach them from the active entry.
                Document.objects.filter(submission_id=instance, is_current=True).update(is_current=False)
                if active_file_names and not attachment_change:
                    attachment_change = {
                        "action": "detached",
                        "previous_files": active_file_names,
                        "new_files": [],
                    }
            if new_status != old_status or attachment_change:
                ReviewLog.objects.create(
                    submission_id=instance,
                    changed_by=request.user,
                    remarks_text=remarks_text,
                    attachment_change=attachment_change,
                    old_status=old_status,
                    new_status=new_status,
                )
            if new_status != old_status and instance.submitted_by and instance.submitted_by.role == "student":
                Notification.objects.create(
                    user_id=instance.submitted_by,
                    submission_id=instance,
                    actor=request.user,
                    type="submission_status_changed",
                    message=f"{instance.title} is now {new_status.replace('_', ' ').title()}.",
                )
            if (
                priority_was_added
                and instance.submitted_by
                and instance.submitted_by.role == "student"
            ):
                Notification.objects.create(
                    user_id=instance.submitted_by,
                    submission_id=instance,
                    actor=request.user,
                    type="submission_priority_changed",
                    message=f"{instance.title} has been marked as a priority submission.",
                )

        # Notify the submitter by email whenever the status actually changed.
        # Sent outside the atomic block, after the DB commit, so a slow or
        # failing mail server never rolls back (or blocks) the review
        # decision itself. Remarks are only included in the email body for
        # resubmission_required -- see submissions/emails.py.
        if new_status != old_status:
            try:
                send_status_change_email(instance, old_status, new_status, remarks_text)
            except Exception:
                logger.exception(
                    "Failed to send status-change email for submission %s",
                    instance.submission_id,
                )

        if priority_was_added and instance.submitted_by and instance.submitted_by.role == "student":
            try:
                send_priority_change_email(instance)
            except Exception:
                logger.exception(
                    "Failed to send priority email for submission %s",
                    instance.submission_id,
                )

        if new_status == Submission.STATUS_APPROVED and (uploaded_files or report_files or drive_folder_id):
            instance.drive_sync_result = self._sync_to_drive(
                request.user, instance, payloads, report_payloads,
                base_folder_id=drive_folder_id or None,
            )
        return instance

    @staticmethod
    def _save_attachment(submission, action, attachment):
        existing = Document.objects.filter(
            submission_id=submission, file_url=attachment["file_url"]
        ).first()
        if action == "replace":
            Document.objects.filter(submission_id=submission, is_current=True).update(is_current=False)
        if existing:
            if not existing.is_current:
                existing.is_current = True
                existing.save(update_fields=["is_current"])
            return
        latest = Document.objects.filter(submission_id=submission).order_by("-version").first()
        Document.objects.create(
            submission_id=submission,
            file_name=attachment["file_name"],
            file_url=attachment["file_url"],
            cloudinary_public_id=attachment["cloudinary_public_id"],
            cloudinary_resource_type=attachment["cloudinary_resource_type"],
            mime_type=attachment["mime_type"],
            file_size_kb=attachment["file_size_kb"],
            version=(latest.version + 1) if latest else 1,
            is_current=True,
        )

    @staticmethod
    def _to_payload(uploaded_file):
        content = uploaded_file.read()
        uploaded_file.seek(0)  # rewind so Cloudinary can still read the stream
        return FilePayload(
            uploaded_file.name,
            content,
            getattr(uploaded_file, "content_type", None) or "application/pdf",
        )

    @staticmethod
    def _upload_to_cloudinary(files):
        """Uploads each file once; returns secure URLs in the same order."""
        uploaded_assets = []
        for f in files:
            try:
                result = cloudinary.uploader.upload(f, folder="vista/documents", resource_type="auto")
            except Exception as exc:
                logger.error("Cloudinary upload failed for %s: %s", f.name, exc)
                raise serializers.ValidationError(
                    {"files": f"Failed to upload '{f.name}'. Please try again."}
                ) from exc
            asset_url = result.get("secure_url") or result.get("url")
            if not asset_url or not result.get("public_id") or result.get("resource_type") not in ("image", "video", "raw"):
                raise serializers.ValidationError(
                    {"files": f"Cloudinary did not return a verifiable asset identity for '{f.name}'."}
                )
            uploaded_assets.append({
                "file_url": asset_url,
                "cloudinary_public_id": result.get("public_id"),
                "cloudinary_resource_type": result.get("resource_type"),
            })
        return uploaded_assets

    @staticmethod
    def _replace_documents(submission, payloads, uploaded_assets):
        Document.objects.filter(submission_id=submission).delete()
        Document.objects.bulk_create(
            Document(
                submission_id=submission,
                file_name=p.name,
                file_url=asset["file_url"],
                cloudinary_public_id=asset["cloudinary_public_id"],
                cloudinary_resource_type=asset["cloudinary_resource_type"],
                mime_type=p.mime_type,
                file_size_kb=max(1, len(p.content) // 1024),
                version=1,
                is_current=True,
            )
            for p, asset in zip(payloads, uploaded_assets)
        )

    @staticmethod
    def _download_current_documents(submission):
        """Fallback when no new files were uploaded: archive what's already stored."""
        payloads = []
        for doc in Document.objects.filter(submission_id=submission, is_current=True):
            try:
                res = requests.get(doc.file_url, timeout=30)
                res.raise_for_status()
                payloads.append(FilePayload(doc.file_name, res.content, doc.mime_type))
            except requests.RequestException as exc:
                logger.warning("Could not fetch %s for Drive sync: %s", doc.document_id, exc)
        return payloads

    def _sync_to_drive(self, user, submission, approved_payloads, report_payloads, base_folder_id=None):
        connection = getattr(user, "drive_connection", None)
        if not (connection and connection.is_active):
            return {"status": "error", "detail": "Connect Google Drive first."}
        try:
            from integrations import google_client  # lazy: Drive libs stay off the import path

            if submission.is_accomplishment_report:
                # Package: the report goes in the Accomplishment Report folder,
                # the approved document in its Approved subfolder.
                batches = [
                    (report_payloads or self._download_current_documents(submission), False),
                    (approved_payloads, True),
                ]
            else:
                batches = [(approved_payloads or self._download_current_documents(submission), False)]

            from integrations.models import DriveArchive

            uploaded_names, failed_names = [], []
            for payloads, approved_copy in batches:
                if not payloads:
                    continue
                folder, path = google_client.resolve_submission_folder_path(
                    connection, submission, approved_copy=approved_copy,
                    base_folder_id=base_folder_id,
                )
                for payload in payloads:
                    try:
                        drive_file = google_client.upload_file_to_folder(
                            connection=connection,
                            folder_id=folder["id"],
                            file_name=payload.name,
                            file_bytes=payload.content,
                            mime_type=payload.mime_type,
                        )
                        drive_file_id = drive_file.get("id") if drive_file else None
                        if not drive_file_id:
                            raise ValueError("Google Drive did not return a file ID.")

                        is_report = submission.is_accomplishment_report and not approved_copy
                        root_folder_id = base_folder_id or connection.folder_id or folder["id"]
                        root_folder_name = (
                            "Selected Drive folder"
                            if base_folder_id and base_folder_id != connection.folder_id
                            else connection.folder_name or "Configured Drive folder"
                        )
                        DriveArchive.objects.update_or_create(
                            submission=submission,
                            drive_file_id=drive_file_id,
                            defaults={
                                "archived_by": user,
                                "file_name": payload.name,
                                "drive_view_link": drive_file.get("webViewLink") or "",
                                "root_folder_id": root_folder_id,
                                "root_folder_name": root_folder_name,
                                "target_folder_id": folder["id"],
                                "folder_path": path or [],
                                "upload_kind": "report" if is_report else "approved",
                            },
                        )
                        uploaded_names.append(payload.name)
                    except google_client.DriveAuthExpired:
                        raise
                    except Exception:
                        logger.exception(
                            "Drive upload or archive-location save failed for %s on submission %s",
                            payload.name,
                            submission.submission_id,
                        )
                        failed_names.append(payload.name)

                logger.info(
                    "Drive sync to %s: %d uploaded, %d failed",
                    path,
                    len(uploaded_names),
                    len(failed_names),
                )

            if uploaded_names and not failed_names:
                connection.last_synced_at = timezone.now()
                connection.save(update_fields=["last_synced_at"])
                return {"status": "success", "uploaded": uploaded_names}
            if uploaded_names:
                return {
                    "status": "partial",
                    "detail": "Some files could not be uploaded to Google Drive.",
                    "uploaded": uploaded_names,
                    "failed": failed_names,
                }
            return {"status": "error", "detail": "No files were available to upload to Google Drive."}
        except google_client.DriveAuthExpired:
            connection.is_active = False
            connection.save(update_fields=["is_active", "updated_at"])
            logger.warning("Google Drive connection expired for user %s", user.pk)
            return {
                "status": "error",
                "code": "drive_reauth_required",
                "detail": "Your Google Drive connection has expired. Please reconnect your account.",
            }
        except Exception:  # Drive problems must never roll back the review decision
            logger.exception("Google Drive sync failed for submission %s", submission.pk)
            return {"status": "error", "detail": "Failed to upload files to Google Drive. Please try again."}
