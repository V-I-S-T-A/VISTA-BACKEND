from types import SimpleNamespace
from unittest.mock import Mock, patch
from contextlib import nullcontext

from django.test import SimpleTestCase
from rest_framework.permissions import IsAuthenticated

from submissions.views import SubmissionDeleteConflict, SubmissionViewSet
from users.permissions import IsAdminOrStaff


class SubmissionDeletionPreflightTests(SimpleTestCase):
    def setUp(self):
        self.submission = SimpleNamespace(submission_id="submission-uuid")

    def test_cloudinary_asset_is_verified_against_its_vista_record(self):
        document = SimpleNamespace(
            file_name="letter.pdf",
            file_url="https://res.cloudinary.com/demo/raw/upload/v42/vista/documents/letter.pdf",
            cloudinary_public_id="vista/documents/letter.pdf",
            cloudinary_resource_type="raw",
        )
        query = Mock()
        query.exclude.return_value.exists.return_value = False
        resource = {
            "public_id": document.cloudinary_public_id,
            "resource_type": document.cloudinary_resource_type,
            "secure_url": document.file_url,
        }

        with patch("submissions.views.Document.objects.filter", return_value=query), patch(
            "submissions.views.cloudinary.api.resource", return_value=resource
        ) as resource_lookup:
            assets = SubmissionViewSet._preflight_submission_assets(
                self.submission, [document]
            )

        self.assertEqual(
            assets,
            [{
                "public_id": document.cloudinary_public_id,
                "resource_type": "raw",
                "exists": True,
            }],
        )
        resource_lookup.assert_called_once_with(
            document.cloudinary_public_id, resource_type="raw"
        )

    def test_legacy_cloudinary_url_without_identity_is_rejected_before_lookup(self):
        document = SimpleNamespace(
            file_name="legacy.pdf",
            file_url="https://res.cloudinary.com/demo/raw/upload/legacy.pdf",
            cloudinary_public_id=None,
            cloudinary_resource_type=None,
        )

        with patch("submissions.views.cloudinary.api.resource") as resource_lookup:
            with self.assertRaises(SubmissionDeleteConflict):
                SubmissionViewSet._preflight_submission_assets(
                    self.submission, [document]
                )

        resource_lookup.assert_not_called()

    def test_shared_cloudinary_reference_blocks_deletion(self):
        document = SimpleNamespace(
            file_name="shared.pdf",
            file_url="https://res.cloudinary.com/demo/raw/upload/shared.pdf",
            cloudinary_public_id="vista/documents/shared.pdf",
            cloudinary_resource_type="raw",
        )
        shared_query = Mock()
        shared_query.exclude.return_value.exists.return_value = True

        with patch(
            "submissions.views.Document.objects.filter", return_value=shared_query
        ), patch("submissions.views.cloudinary.api.resource") as resource_lookup:
            with self.assertRaises(SubmissionDeleteConflict):
                SubmissionViewSet._preflight_submission_assets(
                    self.submission, [document]
                )

        resource_lookup.assert_not_called()

    def test_drive_archive_is_left_alone(self):
        document = SimpleNamespace(
            file_name="archived.pdf",
            file_url="https://drive.google.com/file/d/drive-id/view",
            cloudinary_public_id=None,
            cloudinary_resource_type=None,
        )

        with patch("submissions.views.cloudinary.api.resource") as resource_lookup:
            assets = SubmissionViewSet._preflight_submission_assets(
                self.submission, [document]
            )

        self.assertEqual(assets, [])
        resource_lookup.assert_not_called()

    def test_destroy_requires_authenticated_admin_or_staff(self):
        view = SubmissionViewSet()
        view.action = "destroy"
        permissions = view.get_permissions()
        self.assertTrue(any(isinstance(permission, IsAuthenticated) for permission in permissions))
        staff_permission = next(
            permission for permission in permissions if isinstance(permission, IsAdminOrStaff)
        )
        student_request = SimpleNamespace(
            user=SimpleNamespace(is_authenticated=True, role="student")
        )
        staff_request = SimpleNamespace(
            user=SimpleNamespace(is_authenticated=True, role="staff")
        )
        self.assertFalse(staff_permission.has_permission(student_request, view))
        self.assertTrue(staff_permission.has_permission(staff_request, view))

    def test_missing_exact_confirmation_does_not_delete_submission(self):
        view = SubmissionViewSet()
        submission = Mock(submission_id="submission-uuid")
        view.get_object = Mock(return_value=submission)
        request = SimpleNamespace(data={"confirmation": "delete"})

        with patch("submissions.views.transaction.atomic", return_value=nullcontext()), patch(
            "submissions.views.Submission.objects.select_for_update"
        ) as lock_submission, patch("submissions.views.Document.objects.filter") as document_query:
            response = view.destroy(request)

        self.assertEqual(response.status_code, 400)
        lock_submission.assert_not_called()
        document_query.assert_not_called()
        submission.delete.assert_not_called()

    def test_confirmed_delete_records_reason_and_removes_only_selected_entry(self):
        view = SubmissionViewSet()
        submission = Mock(submission_id="submission-uuid")
        view.get_object = Mock(return_value=submission)
        request = SimpleNamespace(
            data={
                "confirmation": "DELETE",
                "reason_type": "other",
                "reason_details": "Created for the wrong organization",
            },
            user=Mock(),
        )
        locked_submission = Mock(submission_id="submission-uuid")
        lock = Mock()
        lock.get.return_value = locked_submission
        document_query = Mock(return_value=[])

        with patch("submissions.views.transaction.atomic", return_value=nullcontext()), patch(
            "submissions.views.Submission.objects.select_for_update", return_value=lock
        ), patch("submissions.views.Document.objects.filter", document_query), patch(
            "submissions.views.log_delete"
        ) as audit_delete:
            response = view.destroy(request)

        self.assertEqual(response.status_code, 204)
        locked_submission.delete.assert_called_once_with()
        audit_delete.assert_called_once_with(
            user=request.user,
            table_name="tbl_Submissions",
            old_data={
                "submission_id": "submission-uuid",
                "reason": "Other reason: Created for the wrong organization",
                "outcome": "deleted",
            },
        )
