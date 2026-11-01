"""Guards against reintroducing the production branch's duplicate receivers."""
import uuid
from unittest.mock import patch

from django.db import transaction
from django.db.models.signals import post_save
from django.test import TestCase
from rest_framework.test import APIClient

from organizations.models import Organization
from review_logs.models import ReviewLog, ReviewReply
from submissions.models import Submission
from users.models import User


class ReconciledEventContractTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Release test', acronym='RELEASE')
        self.owner = User.objects.create_user(email='owner@release.example.test', first_name='Owner', last_name='Test', org_id=self.org)
        self.peer = User.objects.create_user(email='peer@release.example.test', first_name='Peer', last_name='Test', org_id=self.org)
        self.staff = User.objects.create_user(email='staff@release.example.test', first_name='Staff', last_name='Test', role='staff')
        self.outsider = User.objects.create_user(email='outsider@release.example.test', first_name='Other', last_name='Test')
        self.entry = Submission.objects.create(title='Release entry', submitted_by=self.owner, org_id=self.org, status='under_review')
        self.late_peer = User.objects.create_user(email='late@release.example.test', first_name='Late', last_name='Test', org_id=self.org)
        self.log = ReviewLog.objects.create(submission_id=self.entry, changed_by=self.staff, old_status='under_review', new_status='under_review', remarks_text='Clarify the date.')
        self.client = APIClient()

    def assert_one_event_per_recipient(self, send, event_type):
        calls = [call.args for call in send.call_args_list if call.args[1]['type'] == event_type]
        expected = {'staff_users', f'notifications.{self.owner.pk}', f'notifications.{self.peer.pk}'}
        self.assertEqual(len(calls), len(expected), calls)
        self.assertEqual({group for group, _ in calls}, expected)
        self.assertEqual(len({payload['event_id'] for _, payload in calls}), 1)
        for _, payload in calls:
            self.assertEqual(payload['version'], 1)
            self.assertEqual(payload['submission_id'], str(self.entry.pk))
            self.assertTrue(payload['occurred_at'])
        return calls[0][1]

    def test_only_canonical_review_receivers_are_registered(self):
        for model in [ReviewLog, ReviewReply]:
            sync_receivers, async_receivers = post_save._live_receivers(model)
            receivers = [*sync_receivers, *async_receivers]
            relevant = [receiver for receiver in receivers if receiver.__module__ in ['notifications.signals', 'review_logs.signals']]
            self.assertEqual(len(relevant), 1)
            self.assertEqual(relevant[0].__module__, 'notifications.signals')

    def test_student_and_staff_reply_retry_publish_once_after_commit(self):
        for author in [self.owner, self.staff]:
            with self.subTest(role=author.role), patch('notifications.events.send_group_event') as send:
                self.client.force_authenticate(author)
                payload = {'message': f'{author.role} reply', 'client_request_id': str(uuid.uuid4())}
                path = f'/api/review-logs/{self.log.pk}/replies/'
                with self.captureOnCommitCallbacks(execute=True):
                    first = self.client.post(path, payload, format='json')
                    self.assertEqual(first.status_code, 201, first.data)
                    retry = self.client.post(path, payload, format='json')
                    self.assertEqual(retry.status_code, 200, retry.data)
                    self.assertEqual(first.data['reply_id'], retry.data['reply_id'])
                    send.assert_not_called()
                event = self.assert_one_event_per_recipient(send, 'review_reply.created')
                self.assertEqual(event['reply_id'], first.data['reply_id'])
                self.assertEqual(event['review_log_id'], str(self.log.pk))
                rows = self.client.get(path).data['results']
                self.assertEqual(sum(row['reply_id'] == event['reply_id'] for row in rows), 1)

    @patch('notifications.events.send_group_event')
    def test_same_status_remarks_publish_history_once_without_status_or_notification_event(self, send):
        self.client.force_authenticate(self.staff)
        path = f'/api/submissions/{self.entry.pk}/status/'
        data = {'status': 'under_review', 'remarks_text': 'A new remarks-only update'}
        with self.captureOnCommitCallbacks(execute=True):
            for _ in range(2):
                response = self.client.patch(path, data, format='json')
                self.assertEqual(response.status_code, 200, response.data)
            send.assert_not_called()
        event = self.assert_one_event_per_recipient(send, 'review_log.created')
        self.assertEqual(event['old_status'], event['new_status'])
        self.assertTrue(event['has_remarks'])
        self.assertFalse(any(call.args[1]['type'] in ['submission.updated', 'notification.created'] for call in send.call_args_list))
        history = self.client.get('/api/review-logs/', {'submission_id': str(self.entry.pk)}).data['results']
        self.assertEqual(sum(row['remarks_text'] == data['remarks_text'] for row in history), 1)

    @patch('notifications.events.send_group_event')
    def test_reply_rollback_discards_events_and_saved_reply(self, send):
        request_id = uuid.uuid4()
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    ReviewReply.objects.create(review_log=self.log, author=self.staff, message='Must roll back', client_request_id=request_id)
                    send.assert_not_called()
                    raise RuntimeError('rollback')
        send.assert_not_called()
        self.assertFalse(ReviewReply.objects.filter(client_request_id=request_id).exists())
