"""Commit-safe realtime broadcasts without altering Expo push delivery."""
import logging
from django.db import transaction
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Notification
from .events import dispatch, event_payload, submission_event

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Notification)
def notification_saved(sender, instance, created, update_fields=None, **kwargs):
    kind = "notification.created" if created else "notification.read" if update_fields and "is_read" in update_fields else None
    if kind:
        unread = Notification.objects.filter(user_id_id=instance.user_id_id, is_read=False).count()
        dispatch(event_payload(kind, notification_id=instance.pk,
            submission_id=instance.submission_id_id, id=str(instance.pk),
            unread_count=unread), [f"notifications.{instance.user_id_id}"])

    def publish():
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            async_to_sync(get_channel_layer().group_send)(
                f"notifications.{instance.user_id_id}",
                {"type": "notification.changed", "id": str(instance.pk)})
        except Exception:
            logger.exception("Legacy notification realtime delivery failed")
        if created and settings.NOTIFICATIONS_PUSH_ENABLED:
            try:
                from .tasks import send_push
                send_push.delay(str(instance.pk))
            except Exception:
                logger.exception("Could not queue push notification")
    transaction.on_commit(publish)


@receiver(post_save, sender="submissions.Submission")
def submission_saved(sender, instance, created, **kwargs):
    submission_event("submission.created" if created else "submission.updated", instance,
        **({} if created else {"status": instance.status}))


@receiver(post_save, sender="review_logs.ReviewLog")
def review_log_saved(sender, instance, created, **kwargs):
    if created:
        submission_event("review_log.created", instance.submission_id,
            review_log_id=instance.pk, old_status=instance.old_status,
            new_status=instance.new_status, has_remarks=bool(instance.remarks_text.strip()))


@receiver(post_save, sender="review_logs.ReviewReply")
def review_reply_saved(sender, instance, created, **kwargs):
    if created:
        submission_event("review_reply.created", instance.review_log.submission_id,
            review_log_id=instance.review_log_id, reply_id=instance.pk,
            parent_reply_id=instance.parent_reply_id)
