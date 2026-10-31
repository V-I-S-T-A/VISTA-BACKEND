import logging
import uuid
from datetime import datetime, timezone
from django.db import transaction
from django.utils import timezone as django_timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from users.models import User

logger = logging.getLogger(__name__)

EVENT_SUBMISSION_CREATED = "submission.created"
EVENT_SUBMISSION_UPDATED = "submission.updated"
EVENT_REVIEW_LOG_CREATED = "review_log.created"
EVENT_REVIEW_REPLY_CREATED = "review_reply.created"
EVENT_NOTIFICATION_CREATED = "notification.created"
EVENT_NOTIFICATION_READ = "notification.read"
EVENT_NOTIFICATION_UNREAD_COUNT_CHANGED = "notification.unread_count_changed"

ALL_REALTIME_EVENTS = {
    EVENT_SUBMISSION_CREATED,
    EVENT_SUBMISSION_UPDATED,
    EVENT_REVIEW_LOG_CREATED,
    EVENT_REVIEW_REPLY_CREATED,
    EVENT_NOTIFICATION_CREATED,
    EVENT_NOTIFICATION_READ,
    EVENT_NOTIFICATION_UNREAD_COUNT_CHANGED,
}


def build_event_payload(event_type: str, data: dict, event_id: str | None = None) -> dict:
    """Build a validated, immutable JSON-compatible event payload."""
    if event_type not in ALL_REALTIME_EVENTS:
        raise ValueError(f"Unknown realtime event type: {event_type}")

    if event_id is None:
        event_id = str(uuid.uuid4())

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    payload = {
        "version": 1,
        "event_id": event_id,
        "type": event_type,
        "occurred_at": now_iso,
    }

    # Strict identifier-only whitelisting per event type
    if event_type == EVENT_SUBMISSION_CREATED:
        payload["submission_id"] = str(data["submission_id"])
    elif event_type == EVENT_SUBMISSION_UPDATED:
        payload["submission_id"] = str(data["submission_id"])
        if "status" in data:
            payload["status"] = str(data["status"])
    elif event_type == EVENT_REVIEW_LOG_CREATED:
        payload["submission_id"] = str(data["submission_id"])
        payload["review_log_id"] = str(data["review_log_id"])
        if "old_status" in data:
            payload["old_status"] = str(data["old_status"])
        if "new_status" in data:
            payload["new_status"] = str(data["new_status"])
        if "has_remarks" in data:
            payload["has_remarks"] = bool(data["has_remarks"])
    elif event_type == EVENT_REVIEW_REPLY_CREATED:
        payload["submission_id"] = str(data["submission_id"])
        payload["review_log_id"] = str(data["review_log_id"])
        payload["reply_id"] = str(data["reply_id"])
        payload["parent_reply_id"] = str(data["parent_reply_id"]) if data.get("parent_reply_id") else None
    elif event_type in (EVENT_NOTIFICATION_CREATED, EVENT_NOTIFICATION_READ):
        payload["notification_id"] = str(data["notification_id"])
        payload["submission_id"] = str(data.get("submission_id") or "")
        payload["id"] = str(data["notification_id"])  # legacy backwards compatibility
        if "unread_count" in data:
            payload["unread_count"] = int(data["unread_count"])
    elif event_type == EVENT_NOTIFICATION_UNREAD_COUNT_CHANGED:
        payload["unread_count"] = int(data["unread_count"])

    return payload


def get_submission_recipient_groups(submission) -> set[str]:
    """
    Identifies all channel groups authorized to receive updates about this submission.
    Guarantees:
    - All active staff receive updates via 'staff_users'.
    - The original student submitter receives updates via 'notifications.<student_id>'.
    - Peer students in the same organization receive updates ONLY IF they joined before submission creation.
    - Unrelated students NEVER receive events.
    """
    groups = {"staff_users"}
    if submission.submitted_by_id:
        groups.add(f"notifications.{submission.submitted_by_id}")

    if submission.org_id_id and submission.submitted_at:
        org_students = User.objects.filter(
            org_id=submission.org_id_id,
            org_joined_at__lte=submission.submitted_at,
            role="student",
            is_active=True,
        ).values_list("pk", flat=True)
        for s_id in org_students:
            groups.add(f"notifications.{s_id}")

    return groups


def send_group_event(group: str, payload: dict):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    try:
        async_to_sync(channel_layer.group_send)(
            group,
            {
                "type": "realtime.event",
                "payload": payload,
            },
        )
    except Exception:
        logger.exception("Failed to send realtime event to group %s", group)


def broadcast_submission_created(submission):
    def publish():
        payload = build_event_payload(EVENT_SUBMISSION_CREATED, {"submission_id": submission.pk})
        groups = get_submission_recipient_groups(submission)
        for g in groups:
            send_group_event(g, payload)
    transaction.on_commit(publish)


def broadcast_submission_updated(submission, status=None):
    def publish():
        data = {"submission_id": submission.pk}
        if status:
            data["status"] = status
        payload = build_event_payload(EVENT_SUBMISSION_UPDATED, data)
        groups = get_submission_recipient_groups(submission)
        for g in groups:
            send_group_event(g, payload)
    transaction.on_commit(publish)


def broadcast_review_log_created(log):
    def publish():
        data = {
            "submission_id": log.submission_id_id,
            "review_log_id": log.pk,
            "old_status": log.old_status,
            "new_status": log.new_status,
            "has_remarks": bool(log.remarks_text and log.remarks_text.strip()),
        }
        payload = build_event_payload(EVENT_REVIEW_LOG_CREATED, data)
        groups = get_submission_recipient_groups(log.submission_id)
        for g in groups:
            send_group_event(g, payload)
    transaction.on_commit(publish)


def broadcast_review_reply_created(reply):
    def publish():
        data = {
            "submission_id": reply.review_log.submission_id_id,
            "review_log_id": reply.review_log_id,
            "reply_id": reply.pk,
            "parent_reply_id": reply.parent_reply_id,
        }
        payload = build_event_payload(EVENT_REVIEW_REPLY_CREATED, data)
        groups = get_submission_recipient_groups(reply.review_log.submission_id)
        for g in groups:
            send_group_event(g, payload)
    transaction.on_commit(publish)


def broadcast_notification_created(notification):
    def publish():
        from notifications.models import Notification
        from datetime import timedelta
        cutoff = django_timezone.now() - timedelta(days=30)
        unread_count = Notification.objects.filter(
            user_id=notification.user_id_id, is_read=False, created_at__gte=cutoff
        ).count()
        payload = build_event_payload(
            EVENT_NOTIFICATION_CREATED,
            {
                "notification_id": notification.pk,
                "submission_id": notification.submission_id_id,
                "unread_count": unread_count,
            },
        )
        send_group_event(f"notifications.{notification.user_id_id}", payload)
        # Backwards compatibility notification.changed dispatch
        channel_layer = get_channel_layer()
        if channel_layer:
            try:
                async_to_sync(channel_layer.group_send)(
                    f"notifications.{notification.user_id_id}",
                    {"type": "notification.changed", "id": str(notification.pk)},
                )
            except Exception:
                pass
    transaction.on_commit(publish)


def broadcast_notification_read(notification):
    def publish():
        from notifications.models import Notification
        from datetime import timedelta
        cutoff = django_timezone.now() - timedelta(days=30)
        unread_count = Notification.objects.filter(
            user_id=notification.user_id_id, is_read=False, created_at__gte=cutoff
        ).count()
        payload = build_event_payload(
            EVENT_NOTIFICATION_READ,
            {
                "notification_id": notification.pk,
                "submission_id": notification.submission_id_id,
                "unread_count": unread_count,
            },
        )
        send_group_event(f"notifications.{notification.user_id_id}", payload)
    transaction.on_commit(publish)

