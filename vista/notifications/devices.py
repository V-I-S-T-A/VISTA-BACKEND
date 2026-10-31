"""Binding/revocation uses the existing table; an absent row is inactive."""
import hashlib
from django.core import signing
from django.db import transaction
from .models import PushDevice

SALT = 'vista.push-device.revoke.v1'


def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def revocation_key(device):
    # A narrowly scoped capability, stored by the app in SecureStore. A new
    # owner/binding version invalidates every old owner's revocation key.
    return signing.dumps({'id': device.pk, 'user': str(device.user_id),
        'version': device.updated_at.isoformat(), 'token': token_digest(device.token)}, salt=SALT)


@transaction.atomic
def bind_device(user, token, previous_token=None):
    device, _ = PushDevice.objects.select_for_update().get_or_create(token=token, defaults={'user': user})
    if device.user_id != user.pk:
        device.user = user
        device.save(update_fields=['user', 'updated_at'])
    if previous_token and previous_token != token:
        PushDevice.objects.filter(user=user, token=previous_token).delete()
    return device


def revoke_device(key):
    data = signing.loads(key, salt=SALT, max_age=365 * 24 * 60 * 60)
    with transaction.atomic():
        device = PushDevice.objects.select_for_update().filter(pk=data['id'], user_id=data['user'], updated_at=data['version']).first()
        if device and token_digest(device.token) == data['token']:
            device.delete()
