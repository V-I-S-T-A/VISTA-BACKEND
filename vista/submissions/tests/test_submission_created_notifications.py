from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, call, patch
import uuid

from django.test import SimpleTestCase, override_settings

from submissions.models import Submission
from submissions.serializers import (
    SubmissionCreateSerializer,
    SubmissionStatusUpdateSerializer,
)
from submissions.emails import _submission_url


class SubmissionCreatedNotificationTests(SimpleTestCase):
    def test_new_student_submission_creates_system_notification_and_sends_email(self):
        student = SimpleNamespace(role="student", email="student@example.com")
        request = SimpleNamespace(user=student)
        submission = SimpleNamespace(
            submitted_by=student,
            status=Submission.STATUS_PENDING,
            submission_id="submission-id",
            title="Student activity request",
        )
        serializer = SubmissionCreateSerializer(context={"request": request})

        with patch(
            "submissions.serializers.transaction.atomic", return_value=nullcontext()
        ), patch(
            "submissions.serializers.Submission.objects.create", return_value=submission
        ) as create_submission, patch(
            "submissions.serializers.Notification.objects.create"
        ) as create_notification, patch(
            "submissions.serializers.transaction.on_commit",
            side_effect=lambda callback: callback(),
        ), patch(
            "submissions.serializers.send_status_change_email"
        ) as send_email:
            created = serializer.create({"title": submission.title})

        self.assertIs(created, submission)
        create_submission.assert_called_once_with(
            title=submission.title,
            submitted_by=student,
            status=Submission.STATUS_PENDING,
        )
        create_notification.assert_called_once_with(
            user_id=student,
            submission_id=submission,
            actor=student,
            type="submission_status_changed",
            message="Student activity request has been received and is now Pending.",
        )
        send_email.assert_called_once_with(submission, "new", Submission.STATUS_PENDING)

    def test_staff_creating_submission_for_student_notifies_student(self):
        staff = SimpleNamespace(role="staff", email="staff@example.com")
        student = SimpleNamespace(role="student", email="student@example.com")
        request = SimpleNamespace(user=staff)
        submission = SimpleNamespace(
            submitted_by=student,
            status=Submission.STATUS_PENDING,
            submission_id="sub-123",
            title="Campus Permit Request",
        )
        serializer = SubmissionCreateSerializer(context={"request": request})

        with patch(
            "submissions.serializers.transaction.atomic", return_value=nullcontext()
        ), patch(
            "submissions.serializers.Submission.objects.create", return_value=submission
        ) as create_submission, patch(
            "submissions.serializers.Notification.objects.create"
        ) as create_notification, patch(
            "submissions.serializers.transaction.on_commit",
            side_effect=lambda callback: callback(),
        ), patch(
            "submissions.serializers.send_status_change_email"
        ) as send_email:
            created = serializer.create({"title": submission.title, "submitted_by": student})

        self.assertIs(created, submission)
        create_submission.assert_called_once_with(
            title=submission.title,
            submitted_by=student,
            status=Submission.STATUS_PENDING,
        )
        create_notification.assert_called_once_with(
            user_id=student,
            submission_id=submission,
            actor=staff,
            type="submission_status_changed",
            message="Campus Permit Request has been received and is now Pending.",
        )
        send_email.assert_called_once_with(submission, "new", Submission.STATUS_PENDING)

    def test_submission_by_non_student_does_not_send_notification_or_email(self):
        staff = SimpleNamespace(role="staff", email="staff@example.com")
        request = SimpleNamespace(user=staff)
        submission = SimpleNamespace(
            submitted_by=staff,
            status=Submission.STATUS_PENDING,
            submission_id="sub-456",
            title="Internal Staff Document",
        )
        serializer = SubmissionCreateSerializer(context={"request": request})

        with patch(
            "submissions.serializers.transaction.atomic", return_value=nullcontext()
        ), patch(
            "submissions.serializers.Submission.objects.create", return_value=submission
        ), patch(
            "submissions.serializers.Notification.objects.create"
        ) as create_notification, patch(
            "submissions.serializers.transaction.on_commit",
            side_effect=lambda callback: callback(),
        ), patch(
            "submissions.serializers.send_status_change_email"
        ) as send_email:
            created = serializer.create({"title": submission.title})

        self.assertIs(created, submission)
        create_notification.assert_not_called()
        send_email.assert_not_called()

    def test_initial_submission_email_failure_does_not_block_creation(self):
        student = SimpleNamespace(role="student", email="student@example.com")
        request = SimpleNamespace(user=student)
        submission = SimpleNamespace(
            submitted_by=student,
            status=Submission.STATUS_PENDING,
            submission_id="sub-error",
            title="Activity Letter",
        )
        serializer = SubmissionCreateSerializer(context={"request": request})

        with patch(
            "submissions.serializers.transaction.atomic", return_value=nullcontext()
        ), patch(
            "submissions.serializers.Submission.objects.create", return_value=submission
        ), patch(
            "submissions.serializers.Notification.objects.create"
        ) as create_notification, patch(
            "submissions.serializers.transaction.on_commit",
            side_effect=lambda callback: callback(),
        ), patch(
            "submissions.serializers.send_status_change_email",
            side_effect=RuntimeError("SMTP error"),
        ) as send_email, patch(
            "submissions.serializers.logger.exception"
        ) as log_exc:
            created = serializer.create({"title": submission.title})

        self.assertIs(created, submission)
        create_notification.assert_called_once()
        send_email.assert_called_once()
        log_exc.assert_called_once()

    def test_initial_submission_does_not_duplicate_notifications_or_emails(self):
        student = SimpleNamespace(role="student", email="student@example.com")
        request = SimpleNamespace(user=student)
        submission = SimpleNamespace(
            submitted_by=student,
            status=Submission.STATUS_PENDING,
            submission_id="sub-dedup",
            title="Single Notification Check",
        )
        serializer = SubmissionCreateSerializer(context={"request": request})

        with patch(
            "submissions.serializers.transaction.atomic", return_value=nullcontext()
        ), patch(
            "submissions.serializers.Submission.objects.create", return_value=submission
        ), patch(
            "submissions.serializers.Notification.objects.create"
        ) as create_notification, patch(
            "submissions.serializers.transaction.on_commit",
            side_effect=lambda callback: callback(),
        ), patch(
            "submissions.serializers.send_status_change_email"
        ) as send_email:
            serializer.create({"title": submission.title})

        self.assertEqual(create_notification.call_count, 1)
        self.assertEqual(send_email.call_count, 1)

    def test_subsequent_status_changes_trigger_both_channels(self):
        student = SimpleNamespace(role="student", email="student@example.com")
        staff = SimpleNamespace(role="staff")
        request = SimpleNamespace(user=staff)

        transitions = [
            (Submission.STATUS_PENDING, Submission.STATUS_UNDER_REVIEW, "Under Review"),
            (Submission.STATUS_UNDER_REVIEW, Submission.STATUS_APPROVED, "Approved"),
            (Submission.STATUS_UNDER_REVIEW, Submission.STATUS_REJECTED, "Rejected"),
            (Submission.STATUS_UNDER_REVIEW, Submission.STATUS_RESUBMISSION_REQUIRED, "Resubmission Required"),
        ]

        for old_status, new_status, expected_title in transitions:
            with self.subTest(old_status=old_status, new_status=new_status):
                submission = Mock()
                submission.status = old_status
                submission.submitted_by = student
                submission.priority_escalation = False
                submission.is_accomplishment_report = False
                submission.submission_id = "sub-trans-1"
                submission.title = "Project Proposal"

                serializer = SubmissionStatusUpdateSerializer(
                    submission,
                    data={"status": new_status, "remarks_text": "Review remarks"},
                    context={"request": request},
                )
                serializer.initial_data = {}

                doc_query = Mock()
                doc_query.order_by.return_value.values_list.return_value = []

                with patch(
                    "submissions.serializers.transaction.atomic", return_value=nullcontext()
                ), patch(
                    "submissions.serializers.Document.objects.filter", return_value=doc_query
                ), patch(
                    "review_logs.models.ReviewLog.objects.create"
                ), patch(
                    "submissions.serializers.Notification.objects.create"
                ) as create_notification, patch(
                    "submissions.serializers.send_status_change_email"
                ) as send_email:
                    updated = serializer.update(
                        submission,
                        {"status": new_status, "remarks_text": "Review remarks"},
                    )

                self.assertIs(updated, submission)
                create_notification.assert_called_once_with(
                    user_id=student,
                    submission_id=submission,
                    actor=staff,
                    type="submission_status_changed",
                    message=f"Project Proposal is now {expected_title}.",
                )
                send_email.assert_called_once_with(
                    submission, old_status, new_status, "Review remarks"
                )

    def test_subsequent_status_update_with_same_status_does_not_duplicate_notifications(self):
        student = SimpleNamespace(role="student", email="student@example.com")
        staff = SimpleNamespace(role="staff")
        request = SimpleNamespace(user=staff)

        submission = Mock()
        submission.status = Submission.STATUS_UNDER_REVIEW
        submission.submitted_by = student
        submission.priority_escalation = False
        submission.is_accomplishment_report = False
        submission.submission_id = "sub-same"
        submission.title = "No-Op Status Test"

        serializer = SubmissionStatusUpdateSerializer(
            submission,
            data={"status": Submission.STATUS_UNDER_REVIEW},
            context={"request": request},
        )
        serializer.initial_data = {}

        doc_query = Mock()
        doc_query.order_by.return_value.values_list.return_value = []

        with patch(
            "submissions.serializers.transaction.atomic", return_value=nullcontext()
        ), patch(
            "submissions.serializers.Document.objects.filter", return_value=doc_query
        ), patch(
            "review_logs.models.ReviewLog.objects.create"
        ), patch(
            "submissions.serializers.Notification.objects.create"
        ) as create_notification, patch(
            "submissions.serializers.send_status_change_email"
        ) as send_email:
            serializer.update(submission, {"status": Submission.STATUS_UNDER_REVIEW})

        create_notification.assert_not_called()
        send_email.assert_not_called()

    @override_settings(FRONTEND_URL="https://vista.example.com")
    def test_notification_links_direct_to_student_detail_page(self):
        sub_id = uuid.uuid4()
        submission = SimpleNamespace(submission_id=sub_id)
        url = _submission_url(submission)
        self.assertEqual(url, f"https://vista.example.com/student/review-tracker/{sub_id}")
