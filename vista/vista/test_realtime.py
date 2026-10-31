"""Regression checks for submission-scoped WebSocket authentication and events."""
from unittest.mock import patch
from django.core import signing
from django.test import SimpleTestCase, TestCase

from asgiref.sync import async_to_sync
from vista.realtime import SALT
from vista.realtime_consumers import SubmissionEventsConsumer
from review_logs.realtime_signals import publish_after_commit


class TicketTests(SimpleTestCase):
    def test_invalid_or_expired_ticket_is_rejected(self):
        consumer = SubmissionEventsConsumer()
        self.assertFalse(async_to_sync(consumer.authorize)("not-a-ticket", "abc"))

    def test_mismatched_submission_ticket_is_rejected_without_database_lookup(self):
        token = signing.dumps({"user_id": "someone", "submission_id": "expected"}, salt=SALT)
        consumer = SubmissionEventsConsumer()
        self.assertFalse(async_to_sync(consumer.authorize)(token, "different"))


class BroadcastTests(TestCase):
    def test_commit_sends_minimal_event(self):
        with patch("review_logs.realtime_signals.get_channel_layer") as layer:
            with patch("review_logs.realtime_signals.async_to_sync") as convert:
                with self.captureOnCommitCallbacks(execute=True):
                    publish_after_commit("00000000-0000-0000-0000-000000000001", "review.reply.created")
                layer.assert_called_once()
                convert.assert_called_once_with(layer.return_value.group_send)
                convert.return_value.assert_called_once_with(
                    "submission.00000000-0000-0000-0000-000000000001",
                    {"type": "submission.changed", "change": "review.reply.created"},
                )
