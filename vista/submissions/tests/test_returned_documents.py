from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from submissions.serializers import SubmissionSerializer, SubmissionStatusUpdateSerializer
from submissions.models import Submission


class ReturnedDocumentTests(SimpleTestCase):
    def test_rejected_detail_never_exposes_document_rows(self):
        submission = SimpleNamespace(status=Submission.STATUS_REJECTED)

        with patch("submissions.serializers.Document.objects.filter") as filter_documents:
            documents = SubmissionSerializer(submission).get_documents(submission)

        self.assertEqual(documents, [])
        filter_documents.assert_not_called()

    def test_return_deactivates_current_documents_without_deleting_rows(self):
        submission = Mock()
        submission.status = "under_review"
        submission.submitted_by = None
        document_query = Mock()
        request = SimpleNamespace(user=SimpleNamespace(role="staff"))
        serializer = SubmissionStatusUpdateSerializer(
            submission,
            data={"status": Submission.STATUS_REJECTED},
            context={"request": request},
        )

        with patch("submissions.serializers.transaction.atomic", return_value=nullcontext()), patch(
            "review_logs.models.ReviewLog.objects.create"
        ), patch("submissions.serializers.Document.objects.filter", return_value=document_query) as filter_documents, patch(
            "submissions.serializers.send_status_change_email"
        ):
            updated = serializer.update(submission, {"status": Submission.STATUS_REJECTED})

        self.assertIs(updated, submission)
        filter_documents.assert_called_once_with(
            submission_id=submission,
            is_current=True,
        )
        document_query.update.assert_called_once_with(is_current=False)
        document_query.delete.assert_not_called()
