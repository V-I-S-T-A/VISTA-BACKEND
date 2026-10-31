import logging
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Notification
from submissions.models import Submission
from review_logs.models import ReviewLog, ReviewReply
from .events import (
    broadcast_submission_created,
    broadcast_submission_updated,
    broadcast_review_log_created,
    broadcast_review_reply_created,
    broadcast_notification_created,
    broadcast_notification_read,
)

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Notification)
def notification_saved(sender, instance, created, **kwargs):
    try:
        if created:
            broadcast_notification_created(instance)
        else:
            broadcast_notification_read(instance)
    except Exception:
        logger.exception("Notification realtime delivery failed")

    if created and getattr(settings, "NOTIFICATIONS_PUSH_ENABLED", False):
        def queue_push():
            try:
                from .tasks import send_push
                send_push.delay(str(instance.pk))
            except Exception:
                logger.exception("Could not queue push notification")
        transaction.on_commit(queue_push)


@receiver(post_save, sender=Submission)
def submission_saved(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        broadcast_submission_created(instance)
    except Exception:
        logger.exception("Submission realtime dispatch failed")


@receiver(post_save, sender=ReviewLog)
def review_log_saved(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        broadcast_review_log_created(instance)
        if instance.old_status != instance.new_status:
            broadcast_submission_updated(instance.submission_id, status=instance.new_status)
    except Exception:
        logger.exception("ReviewLog realtime dispatch failed")


@receiver(post_save, sender=ReviewReply)
def review_reply_saved(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        broadcast_review_reply_created(instance)
    except Exception:
        logger.exception("ReviewReply realtime dispatch failed")
