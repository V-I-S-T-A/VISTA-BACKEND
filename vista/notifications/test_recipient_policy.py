"""Personal deliveries and organization tracker access are separate policies."""
import uuid
from unittest.mock import Mock, patch

from django.core import mail
from django.db import transaction
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from notifications.models import Notification, PushDevice
from notifications.tasks import send_push, send_device_push
from organizations.models import Organization
from review_logs.models import ReviewLog
from submissions.models import Submission
from users.models import User


@override_settings(NOTIFICATIONS_PUSH_ENABLED=True, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PersonalNotificationRecipientTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='A and B', acronym='AB')
        other = Organization.objects.create(name='C only', acronym='C')
        self.accounts = {}
        for name, role, org in [('a', 'student', self.org), ('b', 'student', self.org), ('c', 'student', other), ('staff', 'staff', None)]:
            user = User.objects.create_user(email=f'{name}@recipients.example.test', first_name=name, last_name='Fixture', role=role, org_id=org)
            self.accounts[name] = user
            PushDevice.objects.create(user=user, token=f'ExpoPushToken[local-{name}]')
        self.owner = self.accounts['a']
        self.staff = self.accounts['staff']
        self.entry = Submission.objects.create(title='Recipient policy', description='', submitted_by=self.owner, org_id=self.org, status='under_review')
        self.log = ReviewLog.objects.create(submission_id=self.entry, changed_by=self.staff, old_status='under_review', new_status='under_review', remarks_text='A staff remark')
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def write(self, url, payload, method='patch'):
        with patch('notifications.events.send_group_event') as events, patch('notifications.tasks.send_push.delay') as queue:
            with self.captureOnCommitCallbacks(execute=True):
                response = getattr(self.client, method)(url, payload, format='json')
                events.assert_not_called()
                queue.assert_not_called()
            return response, events.call_args_list, queue.call_args_list

    def assert_push_recipients(self, rows, queued, expected_user):
        self.assertEqual({call.args[0] for call in queued}, {str(item.pk) for item in rows})
        self.assertEqual(len(queued), len(rows))
        with patch('notifications.tasks.send_device_push.delay') as schedule:
            for item in rows:
                send_push.run(str(item.pk))
        self.assertEqual(len(schedule.call_args_list), len(rows))
        with patch('notifications.tasks.requests.post') as provider, patch('notifications.tasks.check_push_receipt.apply_async'):
            provider.return_value = Mock(status_code=200, json=lambda: {'data': {'status': 'ok', 'id': str(uuid.uuid4())}})
            for call in schedule.call_args_list:
                self.assertEqual(PushDevice.objects.get(pk=call.args[1]).user_id, expected_user.pk)
                send_device_push.run(*call.args)
            self.assertEqual(len(provider.call_args_list), len(rows))
            self.assertEqual({call.kwargs['json']['to'] for call in provider.call_args_list}, {f'ExpoPushToken[local-{expected_user.first_name}]'})

    def test_all_status_transitions_personal_deliveries_are_submitter_only(self):
        for status in ['approved', 'under_review', 'rejected', 'resubmission_required', 'pending', 'under_review']:
            with self.subTest(status=status):
                before = set(Notification.objects.values_list('pk', flat=True))
                mail.outbox.clear()
                response, events, queue = self.write(f'/api/submissions/{self.entry.pk}/status/', {'status': status, 'remarks_text': f'Move to {status}'})
                self.assertEqual(response.status_code, 200, response.data)
                rows = list(Notification.objects.exclude(pk__in=before))
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0].type, 'submission_status_changed')
                self.assertEqual(rows[0].user_id_id, self.owner.pk)
                self.assertEqual([message.to for message in mail.outbox], [[self.owner.email]])
                self.assert_push_recipients(rows, queue, self.owner)
                personal = [(call.args[0], call.args[1]) for call in events if call.args[1]['type'] == 'notification.created']
                self.assertEqual([group for group, _ in personal], [f'notifications.{self.owner.pk}'])
                tracker = {call.args[0] for call in events if call.args[1]['type'] == 'submission.updated'}
                self.assertEqual(tracker, {'staff_users', f'notifications.{self.owner.pk}', f'notifications.{self.accounts["b"].pk}'})
                for name, user in self.accounts.items():
                    self.client.force_authenticate(user)
                    detail = self.client.get(f'/api/submissions/{self.entry.pk}/')
                    self.assertEqual(detail.status_code, 404 if name == 'c' else 200)
                    if name != 'c':
                        self.assertEqual(detail.data['status'], status)
                    notifications = self.client.get('/api/notifications/').data['results']
                    self.assertEqual(bool(notifications), name == 'a')
                self.client.force_authenticate(self.staff)

    def test_creation_and_priority_personal_channels_remain_submitter_only(self):
        response, events, queue = self.write('/api/submissions/', {'title': 'New personal entry', 'description': '', 'org_id': str(self.org.pk), 'submitted_by': str(self.owner.pk), 'priority_escalation': True}, 'post')
        self.assertEqual(response.status_code, 201, response.data)
        entry = Submission.objects.get(pk=response.data['submission_id'])
        self.assertEqual(entry.status, 'under_review')
        rows = list(Notification.objects.filter(submission_id=entry))
        self.assertEqual({row.type for row in rows}, {'submission_created', 'submission_priority_changed'})
        self.assertEqual({row.user_id_id for row in rows}, {self.owner.pk})
        self.assertEqual([message.to for message in mail.outbox], [[self.owner.email], [self.owner.email]])
        self.assert_push_recipients(rows, queue, self.owner)
        self.assertEqual({call.args[0] for call in events if call.args[1]['type'] == 'notification.created'}, {f'notifications.{self.owner.pk}'})

    def test_remarks_and_identical_retry_create_no_personal_alerts(self):
        for _ in range(2):
            response, events, queue = self.write(f'/api/submissions/{self.entry.pk}/status/', {'status': 'under_review', 'remarks_text': 'Same state, saved remark'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(queue, [])
            self.assertFalse(any(call.args[1]['type'] == 'notification.created' for call in events))
        self.assertEqual(ReviewLog.objects.filter(submission_id=self.entry, remarks_text='Same state, saved remark').count(), 1)
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_first_standard_creation_has_one_initial_history_and_one_personal_delivery(self):
        response, events, queue = self.write('/api/submissions/', {'title': 'First standard submission', 'org_id': str(self.org.pk), 'submitted_by': str(self.owner.pk)}, 'post')
        self.assertEqual(response.status_code, 201, response.data)
        entry_id = response.data['submission_id']
        self.assertEqual(self.client.get(f'/api/submissions/{entry_id}/').data['status'], 'under_review')
        history = self.client.get('/api/review-logs/', {'submission_id': entry_id}).data['results']
        self.assertEqual(len(history), 1)
        self.assertEqual((history[0]['old_status'], history[0]['new_status']), ('under_review', 'under_review'))
        rows = list(Notification.objects.filter(submission_id_id=entry_id))
        self.assertEqual([(row.type, row.user_id_id) for row in rows], [('submission_created', self.owner.pk)])
        self.assertEqual([message.to for message in mail.outbox], [[self.owner.email]])
        self.assert_push_recipients(rows, queue, self.owner)
        self.assertFalse(any(call.args[1]['type'] == 'submission.updated' for call in events))
        self.assertEqual(len([call for call in events if call.args[1]['type'] == 'notification.created']), 1)

    def test_staff_decision_targets_optional_remarks_retries_and_attachment_history(self):
        from documents.models import Document
        document = Document.objects.create(submission_id=self.entry, file_name='local.pdf', file_url='http://127.0.0.1:8275/__manual__/fixture.pdf', mime_type='application/pdf', file_size_kb=1)
        for index, status in enumerate(['approved', 'under_review', 'rejected', 'under_review']):
            before = set(Notification.objects.values_list('pk', flat=True))
            mail.outbox.clear()
            payload = {'status': status}
            if index % 2:
                payload['remarks_text'] = f'Optional remark {index}'
            response, events, queue = self.write(f'/api/submissions/{self.entry.pk}/status/', payload)
            self.assertEqual(response.status_code, 200, response.data)
            rows = list(Notification.objects.exclude(pk__in=before))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].user_id_id, self.owner.pk)
            self.assertEqual([message.to for message in mail.outbox], [[self.owner.email]])
            self.assert_push_recipients(rows, queue, self.owner)
            log_count = ReviewLog.objects.filter(submission_id=self.entry).count()
            mail.outbox.clear()
            retry, _, repeated_queue = self.write(f'/api/submissions/{self.entry.pk}/status/', payload)
            self.assertEqual(retry.status_code, 200)
            self.assertEqual(repeated_queue, [])
            self.assertEqual(len(mail.outbox), 0)
            self.assertEqual(ReviewLog.objects.filter(submission_id=self.entry).count(), log_count)
            self.assertEqual(Notification.objects.exclude(pk__in=before).count(), 1)
            self.assertEqual(self.client.get(f'/api/submissions/{self.entry.pk}/').data['status'], status)
            document.refresh_from_db()
            if index < 2:
                self.assertTrue(document.is_current)
            else:
                self.assertFalse(document.is_current)  # Returned detaches, never deletes history.
            self.assertEqual(Document.objects.filter(pk=document.pk).count(), 1)

    def test_reply_recipient_policy_and_retry_preserved(self):
        self.client.force_authenticate(self.owner)
        payload = {'message': 'Student reply', 'client_request_id': str(uuid.uuid4())}
        response, events, queue = self.write(f'/api/review-logs/{self.log.pk}/replies/', payload, 'post')
        self.assertEqual(response.status_code, 201)
        rows = list(Notification.objects.all())
        self.assertEqual([(row.type, row.user_id_id) for row in rows], [('review_reply_created', self.staff.pk)])
        self.assert_push_recipients(rows, queue, self.staff)
        self.assertEqual({call.args[0] for call in events if call.args[1]['type'] == 'notification.created'}, {f'notifications.{self.staff.pk}'})
        retry, _, queue = self.write(f'/api/review-logs/{self.log.pk}/replies/', payload, 'post')
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(queue, [])
        self.client.force_authenticate(self.staff)
        response, events, queue = self.write(f'/api/review-logs/{self.log.pk}/replies/', {'message': 'Staff reply', 'client_request_id': str(uuid.uuid4())}, 'post')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Notification.objects.count(), 2)
        owner_rows = list(Notification.objects.filter(user_id=self.owner))
        self.assertEqual([row.type for row in owner_rows], ['review_reply_created'])
        self.assert_push_recipients(owner_rows, queue, self.owner)
        self.assertEqual([call.args[0] for call in events if call.args[1]['type'] == 'notification.created'], [f'notifications.{self.owner.pk}'])
        self.assertEqual(len(mail.outbox), 0)  # Neither reply direction schedules email.
        for name in ['b', 'c']:
            self.client.force_authenticate(self.accounts[name])
            result = self.client.post(f'/api/review-logs/{self.log.pk}/replies/', {'message': 'Forbidden', 'client_request_id': str(uuid.uuid4())}, format='json')
            self.assertEqual(result.status_code, 403 if name == 'b' else 404)

    def test_rollback_discards_personal_deliveries(self):
        with patch('notifications.events.send_group_event') as events, patch('notifications.tasks.send_push.delay') as queue:
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(RuntimeError):
                    with transaction.atomic():
                        response = self.client.patch(f'/api/submissions/{self.entry.pk}/status/', {'status': 'approved', 'remarks_text': 'Rolled back'}, format='json')
                        self.assertEqual(response.status_code, 200)
                        raise RuntimeError('rollback')
            events.assert_not_called()
            queue.assert_not_called()
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, 'under_review')
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)
