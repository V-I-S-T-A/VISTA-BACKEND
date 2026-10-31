"""Immutable event identifiers and transaction-safe, recipient-scoped publishing."""
import logging
import uuid
from django.db import transaction
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)
WS_TICKET_SALT = "vista.notifications.ws.ticket.v1"


def event_payload(kind, **fields):
    return {
        "version": 1,
        "event_id": str(uuid.uuid4()),
        "type": kind,
        **{key: str(value) if isinstance(value, uuid.UUID) else value for key, value in fields.items()},
        "occurred_at": timezone.now().isoformat().replace("+00:00", "Z"),
    }


def dispatch(payload, groups):
    groups = tuple(set(groups))
    def publish():
        try:
            layer = get_channel_layer()
            if not layer:
                return
            for group in groups:
                async_to_sync(layer.group_send)(
                    group, {"type": "realtime.event", "payload": payload})
        except Exception:
            logger.exception("Realtime event delivery failed: %s", payload["type"])
    transaction.on_commit(publish)


def submission_groups(submission):
    """Recipients are checked again by the consumer before sending each event."""
    groups = {"staff_users"}
    if submission.submitted_by_id:
        groups.add(f"notifications.{submission.submitted_by_id}")
    if submission.org_id_id:
        from users.models import User
        eligible = User.objects.filter(
            role="student", is_active=True, org_id_id=submission.org_id_id,
            org_joined_at__isnull=False, org_joined_at__lte=submission.submitted_at)
        for user_id in eligible.values_list("pk", flat=True):
            groups.add(f"notifications.{user_id}")
    return groups


def submission_event(kind, submission, **fields):
    dispatch(event_payload(kind, submission_id=submission.pk, **fields), submission_groups(submission))
