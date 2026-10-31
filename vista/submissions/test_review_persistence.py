from unittest.mock import patch
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate
from users.models import User
from review_logs.models import ReviewLog
from review_logs.views import ReviewLogViewSet
from notifications.models import Notification
from .models import Submission
from .views import SubmissionViewSet


@override_settings(NOTIFICATIONS_PUSH_ENABLED=False, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class ReviewPersistenceTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(email='review-staff@example.test', first_name='Staff', last_name='Test', role='staff')
        self.student = User.objects.create_user(email='review-student@example.test', first_name='Student', last_name='Test', role='student')
        self.entry = Submission.objects.create(title='Persistence test', submitted_by=self.student,
                                               status='under_review', priority_escalation=True)
        ReviewLog.objects.create(submission_id=self.entry, changed_by=self.staff,
                                 old_status='pending', new_status='under_review', remarks_text='Ongoing!')
        self.factory = APIRequestFactory()

    def request(self, method, view, data=None, **kwargs):
        request = getattr(self.factory, method)('/api/review-test/', data or {}, format='multipart' if method == 'patch' else None)
        force_authenticate(request, self.staff)
        response = view(request, **kwargs)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def save(self, **data):
        return self.request('patch', SubmissionViewSet.as_view({'patch': 'change_status'}),
                            data, submission_id=self.entry.pk)

    def reload(self):
        entry = self.request('get', SubmissionViewSet.as_view({'get': 'retrieve'}), submission_id=self.entry.pk)
        history = self.request('get', ReviewLogViewSet.as_view({'get': 'list'}),
                               {'submission_id': str(self.entry.pk)})
        return entry, history['results']

    @patch('submissions.serializers.send_status_change_email')
    def test_same_status_new_remarks_survive_fresh_get_requests(self, email):
        self.save(status='under_review', priority_escalation='true', remarks_text='New review note')
        entry, history = self.reload()
        self.assertEqual(entry['status'], 'under_review')
        self.assertTrue(entry['priority_escalation'])
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]['remarks_text'], 'New review note')
        self.assertEqual(history[0]['old_status'], history[0]['new_status'])
        self.assertEqual(history[1]['remarks_text'], 'Ongoing!')
        email.assert_not_called()
        self.assertFalse(Notification.objects.exists())

    def test_retrying_same_note_does_not_duplicate_history(self):
        for _ in range(2):
            self.save(status='under_review', remarks_text='New review note')
        self.assertEqual(ReviewLog.objects.filter(submission_id=self.entry).count(), 2)

    @patch('submissions.serializers.send_status_change_email')
    def test_changed_status_and_remarks_survive_reload_and_notify(self, email):
        with self.captureOnCommitCallbacks(execute=True):
            self.save(status='approved', remarks_text='Verified against original')
        entry, history = self.reload()
        self.assertEqual(entry['status'], 'approved')
        self.assertEqual(history[0]['new_status'], 'approved')
        self.assertEqual(history[0]['remarks_text'], 'Verified against original')
        self.assertEqual(Notification.objects.filter(submission_id=self.entry, type='submission_status_changed').count(), 1)
        email.assert_called_once()

    def test_empty_or_omitted_remarks_do_not_erase_history(self):
        self.save(status='under_review')
        self.save(status='under_review', remarks_text='   ')
        _, history = self.reload()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['remarks_text'], 'Ongoing!')
