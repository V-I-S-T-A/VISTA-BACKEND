from django.core import signing
from django.test import SimpleTestCase
from .events import WS_TICKET_SALT, event_payload


class RealtimeEventTests(SimpleTestCase):
    def test_events_have_stable_versioned_shape(self):
        event = event_payload("review_reply.created", submission_id="abc", reply_id="def")
        self.assertEqual(event["version"], 1)
        self.assertEqual(event["type"], "review_reply.created")
        self.assertEqual(event["submission_id"], "abc")
        self.assertIn("event_id", event)
        self.assertIn("occurred_at", event)

    def test_signed_ticket_can_be_verified(self):
        token = signing.dumps({"user_id": "abc"}, salt=WS_TICKET_SALT)
        self.assertEqual(signing.loads(token, salt=WS_TICKET_SALT, max_age=60)["user_id"], "abc")
