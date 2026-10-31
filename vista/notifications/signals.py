import logging
from django.db import transaction
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Notification

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Notification)
def notification_saved(sender, instance, created, **kwargs):
    def publish():
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            async_to_sync(get_channel_layer().group_send)(
                f'notifications.{instance.user_id_id}',
                {'type': 'notification.changed', 'id': str(instance.pk)},
            )
        except Exception:
            logger.exception('Notification realtime delivery failed')
        if created and settings.NOTIFICATIONS_PUSH_ENABLED:
            try:
                from .tasks import send_push
                send_push.delay(str(instance.pk))
            except Exception:
                logger.exception('Could not queue push notification')
    transaction.on_commit(publish)
