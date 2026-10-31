import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ReviewLog

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
