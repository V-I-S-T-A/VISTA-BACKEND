from datetime import timedelta
import logging
import uuid
import requests
from celery import shared_task
from django.conf import settings
from django.core.cache import caches
from django.db import transaction
from django.utils import timezone
from .models import Notification, PushDevice

logger = logging.getLogger(__name__)
EXPO_URL = 'https://exp.host/--/api/v2/push/'
DELIVERY_TTL = 31 * 24 * 60 * 60


def headers():
    result = {'Content-Type': 'application/json'}
    if settings.EXPO_ACCESS_TOKEN:
        result['Authorization'] = f'Bearer {settings.EXPO_ACCESS_TOKEN}'
    return result


@shared_task
def purge_expired_notifications():
    return Notification.objects.filter(created_at__lt=timezone.now() - timedelta(days=30)).delete()[0]


@shared_task
def send_push(notification_id):
    if not settings.NOTIFICATIONS_PUSH_ENABLED:
        return
    item = Notification.objects.filter(pk=notification_id, created_at__gte=timezone.now() - timedelta(days=30)).first()
    if not item:
        return
    for device in PushDevice.objects.filter(user_id=item.user_id_id):
        send_device_push.delay(str(item.pk), device.pk, device.updated_at.isoformat())


@shared_task(bind=True, max_retries=8)
def send_device_push(self, notification_id, device_id, binding):
    if not settings.NOTIFICATIONS_PUSH_ENABLED:
        return
    cache = caches['push_delivery']
    key = f'{notification_id}:{device_id}:{binding}'
    if cache.get('sent:' + key):
        return
    lease = uuid.uuid4().hex
    if not cache.add('lock:' + key, lease, timeout=60):
        raise self.retry(countdown=15)
    try:
        if cache.get('sent:' + key):
            return
        # Binding changes/unbinding wait for this row lock. Queued work for an
        # earlier owner/version is never delivered to a newly bound account.
        with transaction.atomic():
            device = PushDevice.objects.select_for_update().filter(pk=device_id, updated_at=binding).first()
            item = Notification.objects.filter(pk=notification_id, created_at__gte=timezone.now() - timedelta(days=30)).first()
            if not device or not item or device.user_id != item.user_id_id:
                return
            try:
                response = requests.post(EXPO_URL + 'send', headers=headers(), timeout=15, json={
                    'to': device.token, 'title': 'VISTA notification', 'body': item.message,
                    'sound': 'default', 'channelId': 'vista-updates',
                    'data': {'notification_id': str(item.pk), 'submission_id': str(item.submission_id_id)},
                })
            except requests.RequestException:
                # The provider may already have accepted a timed-out request.
                # Do not resend an ambiguous delivery and create duplicate alerts.
                cache.set('sent:' + key, 'uncertain', timeout=DELIVERY_TTL)
                logger.warning('Push delivery uncertain for notification %s device %s', notification_id, device_id)
                return
            if response.status_code == 429 or response.status_code >= 500:
                raise self.retry(countdown=min(300, 2 ** (self.request.retries + 2)))
            response.raise_for_status()
            ticket = response.json().get('data', {})
            if ticket.get('status') == 'ok' and ticket.get('id'):
                cache.set('sent:' + key, ticket['id'], timeout=DELIVERY_TTL)
                check_push_receipt.apply_async(args=[ticket['id'], device_id, binding], countdown=15 * 60)
            elif ticket.get('details', {}).get('error') == 'DeviceNotRegistered':
                device.delete()
            else:
                # Permanent configuration/payload errors must not resend the batch.
                logger.warning('Push ticket rejected: %s', ticket.get('details', {}).get('error', 'unknown'))
    finally:
        if cache.get('lock:' + key) == lease:
            cache.delete('lock:' + key)


@shared_task(bind=True, max_retries=4)
def check_push_receipt(self, receipt_id, device_id, binding):
    try:
        response = requests.post(EXPO_URL + 'getReceipts', headers=headers(), timeout=15, json={'ids': [receipt_id]})
        if response.status_code == 429 or response.status_code >= 500:
            raise self.retry(countdown=60)
        response.raise_for_status()
    except requests.RequestException as error:
        raise self.retry(exc=error, countdown=60)
    receipt = response.json().get('data', {}).get(receipt_id)
    if not receipt:
        raise self.retry(countdown=60)
    if receipt.get('details', {}).get('error') == 'DeviceNotRegistered':
        PushDevice.objects.filter(pk=device_id, updated_at=binding).delete()
    elif receipt.get('status') == 'error':
        logger.warning('Push receipt rejected: %s', receipt.get('details', {}).get('error', 'unknown'))
