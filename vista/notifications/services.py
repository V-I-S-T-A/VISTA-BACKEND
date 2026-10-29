import logging

from .models import Notification

logger = logging.getLogger(__name__)


def create_drive_upload_notification(user, submission, file_name):
    return Notification.objects.create(
        user_id=user,
        actor=user,
        submission_id=submission,
        type="drive_upload_pending",
        message=f"Uploading {file_name} to Google Drive.",
    )


def update_drive_upload_notification(notification_id, status, message):
    if not notification_id:
        return
    try:
        Notification.objects.filter(notification_id=notification_id).update(
            type=f"drive_upload_{status}",
            message=message,
        )
    except Exception:
        logger.exception(
            "Could not update Drive upload notification %s.", notification_id
        )
