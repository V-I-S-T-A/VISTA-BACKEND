from types import SimpleNamespace
from unittest.mock import patch
from django.core import mail
from django.db import transaction
from django.test import TestCase, override_settings
from users.models import User
from notifications.models import Notification
from .serializers import SubmissionCreateSerializer, SubmissionStatusUpdateSerializer
from .models import Submission


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   NOTIFICATIONS_PUSH_ENABLED=True,
                   CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class CreationNotificationTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(email='receipt-staff@example.test', first_name='Staff', last_name='Test', role='staff')
        self.student = User.objects.create_user(email='receipt-student@example.test', first_name='Student', last_name='Test', role='student')

    def serializer(self):
        serializer = SubmissionCreateSerializer(
            data={'title': 'Activity <request>', 'submitted_by': str(self.student.pk)},
            context={'request': SimpleNamespace(user=self.staff)},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        return serializer

    @patch('notifications.tasks.send_push.delay')
    def test_creation_emails_student_and_queues_native_push_once(self, push):
        with self.captureOnCommitCallbacks(execute=True):
            submission = self.serializer().save()
        item = Notification.objects.get(submission_id=submission)
        self.assertEqual(item.user_id, self.student)
        self.assertEqual(item.actor, self.staff)
        self.assertEqual(item.type, 'submission_created')
        self.assertIn('On Process', item.message)
        self.assertEqual(submission.status, 'under_review')
        push.assert_called_once_with(str(item.pk))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.student.email])
        self.assertIn('has been received', mail.outbox[0].subject)
        self.assertIn('On Process', mail.outbox[0].body)
        self.assertIn('&lt;request&gt;', mail.outbox[0].alternatives[0].content)

    @patch('notifications.tasks.send_push.delay')
    def test_rollback_sends_nothing_and_creates_no_notification(self, push):
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    self.serializer().save()
                    raise ValueError('rollback')
            except ValueError:
                pass
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(len(mail.outbox), 0)
        push.assert_not_called()

    @patch('submissions.serializers.send_submission_received_email', side_effect=RuntimeError('mail unavailable'))
    @patch('notifications.tasks.send_push.delay')
    def test_email_failure_preserves_entry_and_system_notification(self, push, email):
        with self.captureOnCommitCallbacks(execute=True):
            submission = self.serializer().save()
        self.assertTrue(Notification.objects.filter(submission_id=submission).exists())
        push.assert_called_once()

    @patch('notifications.tasks.send_push.delay')
    def test_later_submission_save_does_not_resend_receipt(self, push):
        with self.captureOnCommitCallbacks(execute=True):
            submission = self.serializer().save()
            submission.description = 'Updated description'
            submission.save()
        self.assertEqual(Notification.objects.filter(submission_id=submission).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        push.assert_called_once()

    @patch('notifications.tasks.send_push.delay')
    def test_each_status_change_emails_student_and_queues_push(self, push):
        for old, new in [('under_review', 'approved'), ('under_review', 'rejected'),
                         ('under_review', 'resubmission_required'), ('pending', 'under_review')]:
            with self.subTest(status=new):
                mail.outbox.clear()
                push.reset_mock()
                submission = Submission.objects.create(title='Status test', status=old, submitted_by=self.student)
                serializer = SubmissionStatusUpdateSerializer(submission, data={'status': new},
                    context={'request': SimpleNamespace(user=self.staff)})
                self.assertTrue(serializer.is_valid(), serializer.errors)
                with self.captureOnCommitCallbacks(execute=True):
                    serializer.save()
                item = Notification.objects.get(submission_id=submission)
                self.assertEqual(item.type, 'submission_status_changed')
                self.assertEqual(item.user_id, self.student)
                push.assert_called_once_with(str(item.pk))
                self.assertEqual(len(mail.outbox), 1)
                self.assertEqual(mail.outbox[0].to, [self.student.email])
                if new == 'under_review':
                    self.assertIn('On Process', mail.outbox[0].body)
                    self.assertIn('On Process', item.message)
                push.reset_mock()
                mail.outbox.clear()
                repeated = SubmissionStatusUpdateSerializer(submission, data={'status': new},
                    context={'request': SimpleNamespace(user=self.staff)})
                self.assertTrue(repeated.is_valid(), repeated.errors)
                with self.captureOnCommitCallbacks(execute=True):
                    repeated.save()
                self.assertEqual(Notification.objects.filter(submission_id=submission).count(), 1)
                self.assertEqual(len(mail.outbox), 0)
                push.assert_not_called()

    @patch('notifications.tasks.send_push.delay')
    def test_multipart_status_endpoint_delivers_all_channels(self, push):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from .views import SubmissionViewSet
        submission = Submission.objects.create(title='Endpoint test', status='under_review', submitted_by=self.student)
        request = APIRequestFactory().patch('/api/submissions/status/',
            {'status': 'approved', 'priority_escalation': 'false'}, format='multipart')
        force_authenticate(request, self.staff)
        with self.captureOnCommitCallbacks(execute=True):
            response = SubmissionViewSet.as_view({'patch': 'change_status'})(request, submission_id=submission.pk)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'approved')
        submission.refresh_from_db()
        self.assertEqual(submission.status, 'approved')
        item = Notification.objects.get(submission_id=submission)
        self.assertEqual(item.user_id, self.student)
        push.assert_called_once_with(str(item.pk))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.student.email])
