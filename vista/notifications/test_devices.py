from datetime import timedelta
from unittest.mock import Mock, patch
from django.core.cache import caches
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import User
from submissions.models import Submission
from .models import PushDevice, Notification
from .devices import bind_device
from .tasks import send_push, send_device_push, check_push_receipt


@override_settings(NOTIFICATIONS_PUSH_ENABLED=False)
class DeviceRegistrationTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user(email='push-a@example.com', first_name='Student', last_name='A', role='student')
        self.b = User.objects.create_user(email='push-b@example.com', first_name='Student', last_name='B', role='student')
        self.client = APIClient()
        self.url = reverse('push-devices')
        self.revoke = reverse('push-device-revoke')

    def register(self, user, token='ExpoPushToken[device-one]', **extra):
        self.client.force_authenticate(user)
        return self.client.post(self.url, {'token': token, **extra}, format='json', secure=True)

    def test_authentication_required(self):
        self.assertEqual(self.client.post(self.url, {'token': 'ExpoPushToken[one]'}, format='json').status_code, 401)

    def test_repeated_login_is_idempotent_and_client_user_id_is_ignored(self):
        first = self.register(self.a, user_id=str(self.b.pk))
        self.assertEqual(first.status_code, 200, first.data)
        device = PushDevice.objects.get()
        version = device.updated_at
        second = self.register(self.a)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(PushDevice.objects.count(), 1)
        device.refresh_from_db()
        self.assertEqual(device.user_id, self.a.pk)
        self.assertEqual(device.updated_at, version)

    def test_switch_transfers_ownership_and_old_receipt_cannot_unbind_new_owner(self):
        old = self.register(self.a).data['revoke_key']
        current = self.register(self.b).data['revoke_key']
        self.assertEqual(PushDevice.objects.get().user_id, self.b.pk)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(self.revoke, {'revoke_key': old}).status_code, 204)
        self.assertEqual(PushDevice.objects.count(), 1)
        self.assertEqual(self.client.post(self.revoke, {'revoke_key': current}).status_code, 204)
        self.assertFalse(PushDevice.objects.exists())

    def test_logout_unbinds_only_authenticated_users_token(self):
        self.register(self.a)
        self.client.force_authenticate(self.b)
        self.assertEqual(self.client.delete(self.url, {'token': 'ExpoPushToken[device-one]'}, format='json').status_code, 204)
        self.assertEqual(PushDevice.objects.count(), 1)
        self.client.force_authenticate(self.a)
        self.client.delete(self.url, {'token': 'ExpoPushToken[device-one]'}, format='json')
        self.assertFalse(PushDevice.objects.exists())

    def test_signed_cleanup_works_after_jwt_expiry_and_is_idempotent(self):
        key = self.register(self.a).data['revoke_key']
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer expired-invalid-token')
        for _ in range(2):
            self.assertEqual(self.client.post(self.revoke, {'revoke_key': key}).status_code, 204)
        self.assertEqual(PushDevice.objects.count(), 0)

    def test_invalid_revocation_and_invalid_push_token_are_rejected(self):
        self.register(self.a)
        for token in ('not-a-token', 'ExpoPushToken[]', 'ExpoPushToken[bad token]'):
            self.assertEqual(self.register(self.a, token).status_code, 400)
        self.assertEqual(self.client.post(self.revoke, {'revoke_key': 'forged'}).status_code, 400)
        self.assertEqual(PushDevice.objects.count(), 1)

    def test_rotation_removes_only_the_current_users_previous_token(self):
        self.register(self.a)
        self.register(self.b, 'ExpoPushToken[other-account]')
        result = self.register(self.a, 'ExpoPushToken[device-two]', previous_token='ExpoPushToken[device-one]')
        self.assertEqual(result.status_code, 200)
        self.assertFalse(PushDevice.objects.filter(token='ExpoPushToken[device-one]').exists())
        self.register(self.a, 'ExpoPushToken[device-two]', previous_token='ExpoPushToken[other-account]')
        self.assertEqual(PushDevice.objects.filter(user=self.b).count(), 1)

    def test_real_jwt_refresh_preserves_registration_ownership(self):
        refresh = RefreshToken.for_user(self.a)
        expired = refresh.access_token
        expired.set_exp(lifetime=timedelta(seconds=-30))
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {expired}')
        self.assertEqual(self.client.post(self.url, {'token': 'ExpoPushToken[device-one]'}, format='json').status_code, 401)
        response = self.client.post(reverse('token-refresh'), {'refresh': str(refresh)}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])
        for _ in range(2):
            result = self.client.post(self.url, {'token': 'ExpoPushToken[device-one]'}, format='json')
            self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(PushDevice.objects.get().user_id, self.a.pk)


@override_settings(NOTIFICATIONS_PUSH_ENABLED=True, CACHES={
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
    'push_delivery': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'push-tests'},
})
class PushDeliveryTests(TestCase):
    def setUp(self):
        caches['push_delivery'].clear()
        self.user = User.objects.create_user(email='delivery@example.com', first_name='Test', last_name='User')
        self.other = User.objects.create_user(email='other-delivery@example.com', first_name='Other', last_name='User')
        submission = Submission.objects.create(title='Test entry', description='', submitted_by=self.user)
        self.item = Notification.objects.create(user_id=self.user, submission_id=submission, type='submission_status_changed', message='Updated')
        self.device = bind_device(self.user, 'ExpoPushToken[device-one]')
        self.args = (str(self.item.pk), self.device.pk, self.device.updated_at.isoformat())

    @patch('notifications.tasks.send_device_push.delay')
    def test_fanout_schedules_one_task_per_unique_device(self, delay):
        send_push(str(self.item.pk))
        delay.assert_called_once_with(*self.args)

    @override_settings(NOTIFICATIONS_PUSH_ENABLED=False)
    @patch('notifications.tasks.requests.post')
    def test_disabled_delivery_does_not_contact_expo(self, post):
        send_device_push(*self.args)
        post.assert_not_called()

    @patch('notifications.tasks.check_push_receipt.apply_async')
    @patch('notifications.tasks.requests.post')
    def test_accepted_ticket_is_not_sent_twice(self, post, receipt):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {'data': {'status': 'ok', 'id': 'receipt-one'}}
        send_device_push(*self.args)
        send_device_push(*self.args)
        post.assert_called_once()
        receipt.assert_called_once()

    @patch('notifications.tasks.requests.post')
    def test_queued_old_owner_notification_is_not_delivered_after_switch(self, post):
        bind_device(self.other, self.device.token)
        send_device_push(*self.args)
        post.assert_not_called()

    @patch('notifications.tasks.requests.post')
    def test_unbound_device_is_never_sent_to(self, post):
        self.device.delete()
        send_device_push(*self.args)
        post.assert_not_called()

    @patch('notifications.tasks.requests.post')
    def test_device_not_registered_ticket_unbinds_invalid_token(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {'data': {'status': 'error', 'details': {'error': 'DeviceNotRegistered'}}}
        send_device_push(*self.args)
        self.assertFalse(PushDevice.objects.exists())

    @patch('notifications.tasks.requests.post')
    def test_expired_receipt_unbinds_only_matching_version(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {'data': {'receipt-one': {'status': 'error', 'details': {'error': 'DeviceNotRegistered'}}}}
        bind_device(self.other, self.device.token)
        check_push_receipt('receipt-one', self.args[1], self.args[2])
        self.assertEqual(PushDevice.objects.get().user_id, self.other.pk)

    @patch('notifications.tasks.requests.post')
    def test_ambiguous_timeout_is_not_retried_as_a_duplicate(self, post):
        import requests
        post.side_effect = requests.Timeout()
        send_device_push(*self.args)
        send_device_push(*self.args)
        post.assert_called_once()
