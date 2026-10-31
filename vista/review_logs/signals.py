import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ReviewLog, ReviewReply

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ReviewLog)
def review_log_saved(sender, instance, created, **kwargs):
    if (
        not created
        or instance.old_status != instance.new_status
        or (not instance.remarks_text.strip() and not instance.attachment_change)
    ):
        return
    recipient_id = instance.submission_id.submitted_by_id
    if not recipient_id:
        return

    def publish():
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            async_to_sync(get_channel_layer().group_send)(
                f"notifications.{recipient_id}",
                {"type": "notification.changed", "id": str(instance.pk)},
            )
        except Exception:
            logger.exception("Review history realtime delivery failed")

    transaction.on_commit(publish)


@receiver(post_save, sender=ReviewReply)
def staff_reply_saved(sender, instance, created, **kwargs):
    if not created or not instance.author or instance.author.role not in ("staff", "admin"):
        return

    submission = instance.review_log.submission_id
    recipient_id = submission.submitted_by_id
    if not recipient_id or recipient_id == instance.author_id:
        return

    def publish():
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            async_to_sync(get_channel_layer().group_send)(
                f"notifications.{recipient_id}",
                {
                    "type": "notification.changed",
                    "event_type": "review_reply.created",
                    "id": str(instance.pk),
                    "review_log_id": str(instance.review_log_id),
                },
            )
        except Exception:
            logger.exception("Staff reply realtime delivery failed")

    transaction.on_commit(publish)
