"""Actual API writes/fresh reads with isolated storage and captured delivery."""
import builtins
from types import SimpleNamespace
from unittest.mock import patch
from django.core import mail
from django.db import transaction
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from notifications.models import Notification
from review_logs.models import ReviewLog
from users.models import User
from .models import Submission
from .serializers import SubmissionStatusUpdateSerializer


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   NOTIFICATIONS_PUSH_ENABLED=True,
                   CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class LocalNotificationFlowTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(email='flow-staff@example.test', first_name='Staff', last_name='Test', role='staff')
        self.student = User.objects.create_user(email='flow-owner@example.test', first_name='Owner', last_name='Test', role='student')
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def entry(self, status='under_review'):
        return Submission.objects.create(title='Flow test', submitted_by=self.student, status=status)

    def update(self, entry, **data):
        response = self.client.patch(f'/api/submissions/{entry.pk}/status/', data, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        return response

    @patch('notifications.tasks.send_push.delay')
    def test_creation_saves_on_process_history_and_one_receipt_for_each_channel(self, push):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post('/api/submissions/', {'title': 'Created entry', 'submitted_by': str(self.student.pk)}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        entry = Submission.objects.get(pk=response.data['submission_id'])
        self.assertEqual(self.client.get(f'/api/submissions/{entry.pk}/').data['status'], 'under_review')
        history = self.client.get('/api/review-logs/', {'submission_id': str(entry.pk)}).data['results']
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['new_status'], 'under_review')
        event = Notification.objects.get(submission_id=entry)
        self.assertEqual(event.user_id, self.student)
        self.assertEqual(event.type, 'submission_created')
        push.assert_called_once_with(str(event.pk))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.student.email])

    @patch('notifications.tasks.send_push.delay')
    def test_all_seventeen_supported_transitions_persist_and_dispatch_once(self, push):
        transitions = {
            'pending': ['under_review', 'approved', 'rejected', 'resubmission_required'],
            'under_review': ['approved', 'rejected', 'resubmission_required'],
            'resubmission_required': ['under_review', 'pending', 'approved', 'rejected'],
            'approved': ['under_review', 'resubmission_required', 'rejected'],
            'rejected': ['under_review', 'resubmission_required', 'approved'],
        }
        for before, destinations in transitions.items():
            for after in destinations:
                with self.subTest(before=before, after=after):
                    entry = self.entry(before)
                    mail.outbox.clear()
                    push.reset_mock()
                    with self.captureOnCommitCallbacks(execute=True):
                        for _ in range(2):
                            self.update(entry, status=after, remarks_text='Saved review')
                    self.assertEqual(self.client.get(f'/api/submissions/{entry.pk}/').data['status'], after)
                    history = self.client.get('/api/review-logs/', {'submission_id': str(entry.pk)}).data['results']
                    self.assertEqual(len(history), 1)
                    self.assertEqual(history[0]['remarks_text'], 'Saved review')
                    event = Notification.objects.get(submission_id=entry)
                    self.assertEqual(event.user_id, self.student)
                    push.assert_called_once_with(str(event.pk))
                    self.assertEqual(len(mail.outbox), 1)
                    self.assertEqual(mail.outbox[0].to, [self.student.email])

    @patch('notifications.tasks.send_push.delay')
    def test_outer_rollback_does_not_email_or_queue_push(self, push):
        entry = self.entry()
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(ValueError):
                with transaction.atomic():
                    self.update(entry, status='approved', priority_escalation='true')
                    raise ValueError('rollback')
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'under_review')
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(ReviewLog.objects.exists())
        self.assertEqual(len(mail.outbox), 0)
        push.assert_not_called()

    @patch('notifications.tasks.send_push.delay')
    def test_stale_prevalidated_retry_does_not_duplicate_delivery(self, push):
        entry = self.entry()
        serializers = [SubmissionStatusUpdateSerializer(Submission.objects.get(pk=entry.pk),
            data={'status': 'approved', 'remarks_text': 'Verified'},
            context={'request': SimpleNamespace(user=self.staff)}) for _ in range(2)]
        for serializer in serializers:
            self.assertTrue(serializer.is_valid(), serializer.errors)
        with self.captureOnCommitCallbacks(execute=True):
            for serializer in serializers:
                serializer.save()
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(ReviewLog.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        push.assert_called_once()

    @patch('notifications.tasks.send_push.delay')
    def test_realtime_import_failure_cannot_cancel_email_or_push(self, push):
        original_import = builtins.__import__
        def failing_import(name, *args, **kwargs):
            if name == 'channels.layers':
                raise ImportError('simulated realtime dependency failure')
            return original_import(name, *args, **kwargs)
        entry = self.entry()
        with patch('builtins.__import__', side_effect=failing_import):
            with self.captureOnCommitCallbacks(execute=True):
                self.update(entry, status='approved')
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        push.assert_called_once()

    @patch('notifications.tasks.send_push.delay', side_effect=RuntimeError('simulated broker outage'))
    def test_push_queue_failure_does_not_cancel_email(self, push):
        entry = self.entry()
        with self.captureOnCommitCallbacks(execute=True):
            self.update(entry, status='approved')
        self.assertEqual(Notification.objects.filter(submission_id=entry).count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    @patch('notifications.tasks.send_push.delay')
    def test_creation_history_failure_rolls_back_without_dispatch(self, push):
        with self.captureOnCommitCallbacks(execute=True):
            with patch('review_logs.models.ReviewLog.objects.create', side_effect=ValueError('simulated write failure')):
                with self.assertRaises(ValueError):
                    self.client.post('/api/submissions/', {'title': 'Must roll back', 'submitted_by': str(self.student.pk)}, format='json')
        self.assertFalse(Submission.objects.exists())
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(len(mail.outbox), 0)
        push.assert_not_called()

    @patch('notifications.tasks.send_push.delay')
    def test_return_retains_attachment_record_and_fresh_details_hide_it(self, push):
        from documents.models import Document
        entry = self.entry()
        document = Document.objects.create(submission_id=entry, file_name='retained.webp',
            file_url='https://example.test/retained.webp', mime_type='image/webp', file_size_kb=1)
        with self.captureOnCommitCallbacks(execute=True):
            self.update(entry, status='rejected', remarks_text='Return for correction')
        document.refresh_from_db()
        self.assertFalse(document.is_current)
        self.assertTrue(Document.objects.filter(pk=document.pk).exists())
        self.assertEqual(self.client.get(f'/api/submissions/{entry.pk}/').data['documents'], [])
