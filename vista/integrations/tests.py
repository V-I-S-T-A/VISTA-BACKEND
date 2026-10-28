from contextlib import nullcontext
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from integrations.tasks import upload_document_to_drive
from submissions.models import Submission


class DelayedDriveApprovalTaskTests(SimpleTestCase):
    def test_does_not_reactivate_attachment_if_submission_was_returned_during_upload(self):
        connection = Mock(folder_id="archive-folder")
        submission = Mock(
            status=Submission.STATUS_APPROVED,
            is_accomplishment_report=False,
            submission_id="submission-uuid",
            academic_year_id=None,
            org_id=None,
            doc_type_id=None,
        )
        returned_submission = Mock(
            status=Submission.STATUS_REJECTED,
            submission_id="submission-uuid",
        )
        cloudinary_copy = {
            "secure_url": "https://res.cloudinary.com/example/raw/upload/approved.pdf",
            "public_id": "approved_submission-uuid_drive-file.pdf",
            "resource_type": "raw",
        }
        archive = Mock(
            archive_id="archive-uuid",
            root_folder_name="Archive",
            root_folder_id="archive-folder",
            target_folder_id="archive-folder",
            folder_path=["Academic Year"],
            file_name="approved.pdf",
            drive_view_link="https://drive.google.com/file/d/drive-file/view",
        )

        with patch("integrations.models.GoogleDriveConnection.objects.get", return_value=connection), patch(
            "submissions.models.Submission.objects.select_related"
        ) as submission_query, patch(
            "submissions.models.Submission.objects.select_for_update"
        ) as locked_submission_query, patch("users.models.User.objects.filter") as user_query, patch(
            "integrations.tasks.google_client.resolve_submission_folder_path",
            return_value=({"id": "archive-folder"}, ["Academic Year"]),
        ), patch(
            "integrations.tasks.google_client.upload_file_to_folder",
            return_value={"id": "drive-file", "webViewLink": "https://drive.google.com/file/d/drive-file/view"},
        ), patch(
            "integrations.tasks.DriveArchive.objects.update_or_create",
            return_value=(archive, True),
        ), patch("cloudinary.uploader.upload", return_value=cloudinary_copy), patch(
            "integrations.tasks.transaction.atomic", return_value=nullcontext()
        ), patch("documents.models.Document.objects.create") as document_create, patch(
            "documents.models.Document.objects.filter"
        ) as document_filter, patch("audit_logs.utility.log_create"):
            submission_query.return_value.get.return_value = submission
            locked_submission_query.return_value.get.return_value = returned_submission
            user_query.return_value.first.return_value = Mock()

            result = upload_document_to_drive.run(
                staff_user_id="staff-test",
                submission_id="submission-uuid",
                file_b64="Ynl0ZXM=",
                file_name="approved.pdf",
                mime_type="application/pdf",
                use_auto_folder=True,
                manual_folder_id=None,
                upload_kind="approved",
            )

        self.assertEqual(result["status"], "success")
        self.assertIn("no longer approved", result["detail"])
        self.assertIsNone(result["document"])
        document_create.assert_not_called()
        document_filter.assert_not_called()
