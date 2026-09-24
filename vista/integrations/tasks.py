import logging

from celery import shared_task
from django.utils import timezone

from .models import GoogleDriveConnection
from . import google_client
from .google_client import DriveAuthExpired

logger = logging.getLogger(__name__)


def _sanitize_folder_name(name, fallback="Unknown"):
    if not name:
        return fallback
    return str(name).replace("/", "-").strip() or fallback


@shared_task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
)
def sync_submission_to_drive(self, submission_id, staff_user_id):
    from submissions.models import Submission
    from documents.models import Document

    try:
        submission = Submission.objects.select_related(
            "org_id", "category_id", "doc_type_id", "academic_year_id"
        ).get(submission_id=submission_id)
    except Submission.DoesNotExist:
        logger.warning("Submission %s no longer exists, skipping Drive sync.", submission_id)
        return

    try:
        connection = GoogleDriveConnection.objects.get(staff_id=staff_user_id, is_active=True)
    except GoogleDriveConnection.DoesNotExist:
        logger.warning("No active Drive connection for staff %s, skipping sync.", staff_user_id)
        return

    if not connection.folder_id:
        logger.warning("Staff %s has not configured a Drive folder yet.", staff_user_id)
        return

    documents = Document.objects.filter(submission_id=submission, is_current=True)
    if not documents.exists():
        logger.info("Submission %s has no current documents to sync.", submission_id)
        return

    year_name = _sanitize_folder_name(
        submission.academic_year_id.year if submission.academic_year_id else None,
        fallback="Unspecified Year",
    )
    org_name = _sanitize_folder_name(
        submission.org_id.acronym if submission.org_id else None,
        fallback="Unspecified Organization",
    )
    doc_type_name = _sanitize_folder_name(
        submission.doc_type_id.name if submission.doc_type_id else None,
        fallback="Unspecified Document Type",
    )

    try:
        target_folder_id = google_client.ensure_folder_path(
            connection,
            connection.folder_id,
            [year_name, org_name, doc_type_name],
        )

        for document in documents:
            import requests

            file_response = requests.get(document.file_url, timeout=30)
            file_response.raise_for_status()

            google_client.upload_file_to_folder(
                connection=connection,
                folder_id=target_folder_id,
                file_name=document.file_name,
                file_bytes=file_response.content,
                mime_type=document.mime_type,
            )
    except DriveAuthExpired:
        # No amount of retrying fixes a revoked/expired grant -- deactivate
        # the connection right away instead of retrying against a dead
        # token for up to 10 minutes (retry_backoff_max=600) and failing
        # anyway. The staff member gets a clean "reconnect" prompt next
        # time they open Google Drive Sync.
        logger.warning(
            "Drive connection for staff %s has expired or been revoked; deactivating.",
            staff_user_id,
        )
        connection.is_active = False
        connection.save(update_fields=["is_active", "updated_at"])
        return

    connection.last_synced_at = timezone.now()
    connection.save(update_fields=["last_synced_at"])

    logger.info(
        "Synced submission %s to Drive folder %s/%s/%s/%s.",
        submission_id, connection.folder_name, year_name, org_name, doc_type_name,
    )


@shared_task(bind=True)
def upload_document_to_drive(
    self,
    staff_user_id,
    submission_id,
    file_b64,
    file_name,
    mime_type,
    use_auto_folder=True,
    manual_folder_id=None,
):
    """
    Backs the manual "Archive to Google Drive" button on the Review Panel.
    Runs off the request/response cycle so a slow connection doesn't block
    the staff member from doing anything else -- DriveSubmissionUploadView
    enqueues this and returns immediately; the app polls
    DriveUploadStatusView for the result below.
    """
    import base64

    from documents.models import Document
    from documents.serializers import DocumentSerializer
    from submissions.models import Submission

    try:
        connection = GoogleDriveConnection.objects.get(staff_id=staff_user_id, is_active=True)
    except GoogleDriveConnection.DoesNotExist:
        return {
            "status": "error",
            "code": "drive_reauth_required",
            "detail": "Connect Google Drive first.",
        }

    try:
        submission = Submission.objects.select_related(
            "academic_year_id", "org_id", "doc_type_id"
        ).get(submission_id=submission_id)
    except Submission.DoesNotExist:
        return {"status": "error", "detail": "Submission not found."}

    if submission.status != Submission.STATUS_APPROVED:
        return {"status": "error", "detail": "Only approved submissions can be archived to Drive."}

    file_bytes = base64.b64decode(file_b64)
    path_segments = None

    try:
        if use_auto_folder or not manual_folder_id:
            folder, path_segments = google_client.resolve_submission_folder_path(
                connection, submission, approved_copy=True
            )
            target_folder_id = folder["id"]
        else:
            target_folder_id = manual_folder_id

        uploaded = google_client.upload_file_to_folder(
            connection=connection,
            folder_id=target_folder_id,
            file_name=file_name,
            file_bytes=file_bytes,
            mime_type=mime_type,
        )
    except DriveAuthExpired:
        connection.is_active = False
        connection.save(update_fields=["is_active", "updated_at"])
        return {
            "status": "error",
            "code": "drive_reauth_required",
            "detail": "Your Google Drive connection has expired. Please reconnect your Google account.",
        }
    except Exception:
        logger.exception("Manual Drive archive failed for submission %s", submission_id)
        return {"status": "error", "detail": "Failed to upload the file to Google Drive. Please try again."}

    Document.objects.filter(submission_id=submission, is_current=True).update(is_current=False)
    latest = Document.objects.filter(submission_id=submission).order_by("-version").first()
    next_version = (latest.version + 1) if latest else 1

    document = Document.objects.create(
        submission_id=submission,
        file_name=file_name,
        file_url=uploaded.get("webViewLink", ""),
        mime_type=mime_type,
        file_size_kb=max(1, len(file_bytes) // 1024),
        version=next_version,
        is_current=True,
    )

    connection.last_synced_at = timezone.now()
    connection.save(update_fields=["last_synced_at"])

    return {
        "status": "success",
        "detail": "Document archived to Google Drive.",
        "drive_file_id": uploaded.get("id"),
        "drive_view_link": uploaded.get("webViewLink"),
        "folder_path": path_segments,
        "document": DocumentSerializer(document).data,
    }