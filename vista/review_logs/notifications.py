import logging
from notifications.models import Notification
from .models import ReviewLog

logger = logging.getLogger(__name__)


def get_responsible_staff_for_reply(reply):
    """
    Identifies the authorized staff/admin member responsible for the review entry or submission.

    Resolution order:
    1. If the reply is a followup to a staff parent_reply, that staff author.
    2. The staff member who authored the remark on this ReviewLog entry (log.changed_by).
    3. The most recent active staff reviewer on this submission.

    Guarantees:
    - Never returns the reply author (no self-notification).
    - Only returns active staff/admin users.
    - Never returns other organization members.
    - Never guesses or returns arbitrary users if responsibility cannot be resolved.
    """
    log = reply.review_log
    author = reply.author
    submission = log.submission_id

    # 1. Followup parent reply author if active staff and not self
    if reply.parent_reply_id:
        parent = reply.parent_reply
        if (
            parent
            and parent.author_id
            and parent.author_id != author.pk
            and parent.author.role in ("staff", "admin")
            and parent.author.is_active
        ):
            return parent.author

    # 2. Staff who authored the remark on this ReviewLog entry
    log_author = log.changed_by
    if (
        log_author
        and log_author.pk != author.pk
        and log_author.role in ("staff", "admin")
        and log_author.is_active
    ):
        return log_author

    # 3. Fallback: most recent active staff reviewer on this submission
    latest_review = (
        ReviewLog.objects.filter(
            submission_id=submission,
            changed_by__role__in=["staff", "admin"],
            changed_by__is_active=True,
        )
        .exclude(changed_by=author)
        .order_by("-changed_at")
        .first()
    )
    if latest_review and latest_review.changed_by:
        return latest_review.changed_by

    logger.warning(
        "Could not resolve an authorized staff recipient for student reply %s on submission %s (log %s).",
        reply.pk,
        submission.pk,
        log.pk,
    )
    return None


def notify_staff_of_reply(reply):
    """
    Creates an in-app system notification for the responsible staff member when a student replies.

    Must be called inside the active transaction so that rollback cancels the notification.
    """
    recipient = get_responsible_staff_for_reply(reply)
    if not recipient:
        return None

    author_name = reply.author.full_name if reply.author else "A student"
    submission = reply.review_log.submission_id
    title = (submission.title or "").strip()
    if title:
        message = f'{author_name} replied to your remark on "{title}".'
    else:
        message = f'{author_name} replied to your remark.'

    return Notification.objects.create(
        user_id=recipient,
        actor=reply.author,
        submission_id=submission,
        type="review_reply_created",
        message=message,
    )

