import logging

from celery import shared_task
from django.utils import timezone

from .models import GoogleDriveConnection
from . import google_client

logger = logging.getLogger(__name__)


def _sanitize_folder_name(name, fallback="Unknown"):
    """
    Drive folder names can't contain "/" (some clients mangle it as a path
    separator), and a blank name is worse than a clear fallback -- so both
    get normalized here before being used as a path segment.
    """
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

    # Build <Base>/<Year>/<Org>/<DocType>/ under the staff's configured base
    # folder, creating any missing segments automatically. find_or_create
    # semantics mean re-syncing the same submission reuses the same folders
    # instead of duplicating them.
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

    connection.last_synced_at = timezone.now()
    connection.save(update_fields=["last_synced_at"])

    logger.info(
        "Synced submission %s to Drive folder %s/%s/%s/%s.",
        submission_id, connection.folder_name, year_name, org_name, doc_type_name,
    )