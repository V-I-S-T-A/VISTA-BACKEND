"""Notify viewers only after a reply or status-history entry commits."""
import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ReviewLog, ReviewReply

logger = logging.getLogger(__name__)

def publish_after_commit(submission_id, change):
    def send():
        try:
            layer = get_channel_layer()
            if layer:
                async_to_sync(layer.group_send)(
                    f"submission.{submission_id}",
                    {"type": "submission.changed", "change": change}
                )
        except Exception:
            logger.exception("Realtime submission event failed for %s", submission_id)
    transaction.on_commit(send)

@receiver(post_save, sender=ReviewLog, dispatch_uid="vista.realtime.review_log")
def review_log_created(sender, instance, created, **kwargs):
    if created:
        publish_after_commit(instance.submission_id_id, "review.log.created")

@receiver(post_save, sender=ReviewReply, dispatch_uid="vista.realtime.review_reply")
def review_reply_created(sender, instance, created, **kwargs):
    if created:
        publish_after_commit(instance.review_log.submission_id_id, "review.reply.created")
