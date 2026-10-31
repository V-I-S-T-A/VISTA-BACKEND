from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from django.test import TestCase as DatabaseTestCase
from rest_framework.exceptions import ValidationError
from .serializers import SubmissionCreateSerializer


class PriorityEntryPermissionTests(TestCase):
    def serializer(self, role):
        return SubmissionCreateSerializer(context={'request': SimpleNamespace(user=SimpleNamespace(role=role))})

    def test_student_cannot_prioritize_a_submission(self):
        with self.assertRaises(ValidationError):
            self.serializer('student').validate({'priority_escalation': True})

    def test_staff_and_admin_can_prioritize(self):
        for role in ('staff', 'admin'):
            self.assertTrue(self.serializer(role).validate({'priority_escalation': True})['priority_escalation'])

    def test_standard_entry_is_unchanged(self):
        self.assertEqual(self.serializer('student').validate({}), {})


class PriorityCreationTests(DatabaseTestCase):
    @patch('submissions.serializers.send_priority_change_email')
    def test_priority_entry_creates_one_notification_and_email(self, send_email):
        from users.models import User
        from notifications.models import Notification
        staff = User.objects.create_user(email='staff-priority@example.com', first_name='Staff', last_name='User', role='staff')
        student = User.objects.create_user(email='student-priority@example.com', first_name='Student', last_name='User', role='student')
        serializer = SubmissionCreateSerializer(data={'title': 'Priority entry', 'priority_escalation': True, 'submitted_by': str(student.pk)}, context={'request': SimpleNamespace(user=staff)})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        with self.captureOnCommitCallbacks(execute=True):
            submission = serializer.save()
        self.assertTrue(submission.priority_escalation)
        self.assertEqual(submission.status, 'under_review')
        self.assertEqual(Notification.objects.filter(submission_id=submission, type='submission_priority_changed', user_id=student).count(), 1)
        send_email.assert_called_once_with(submission)
