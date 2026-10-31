"""Read-only real-time subscription: all writes remain on the existing REST endpoints."""
from urllib.parse import parse_qs
from django.contrib.auth import get_user_model
from django.core import signing
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from submissions.models import Submission
from submissions.visibility import can_read_submission
from .realtime import SALT

class SubmissionEventsConsumer(AsyncJsonWebsocketConsumer):
    @database_sync_to_async
    def authorize(self, ticket, submission_id):
        try:
            payload = signing.loads(ticket, salt=SALT, max_age=45)
            if payload.get("submission_id") != str(submission_id):
                return False
            user = get_user_model().objects.get(pk=payload["user_id"], is_active=True)
            submission = Submission.objects.get(pk=submission_id)
            return can_read_submission(user, submission)
        except (signing.BadSignature, signing.SignatureExpired, ValueError, TypeError,
                get_user_model().DoesNotExist, Submission.DoesNotExist):
            return False

    async def connect(self):
        self.submission_id = str(self.scope["url_route"]["kwargs"]["submission_id"])
        ticket = parse_qs(self.scope.get("query_string", b"").decode()).get("ticket", [""])[0]
        if not await self.authorize(ticket, self.submission_id):
            await self.close(code=4403)
            return
        self.group_name = f"submission.{self.submission_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def submission_changed(self, event):
        # Send only IDs / event names. Fetch actual content through permission-checked REST APIs.
        await self.send_json({"type": "submission.changed",
                              "submission_id": self.submission_id,
                              "change": event["change"]})
