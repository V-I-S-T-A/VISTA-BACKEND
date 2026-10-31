"""Shared notification WebSocket contract for web and mobile clients."""
import asyncio
from datetime import datetime, timezone
from django.contrib.auth import get_user_model
from django.core import signing
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework.exceptions import AuthenticationFailed
from .events import WS_TICKET_SALT


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.authenticated = False
        self.expiry_task = None
        self.auth_timer = None
        self.joined = []
        await self.accept()
        user = self.scope.get("user")
        if user and user.is_authenticated and await self.active_user(user.pk):
            await self.activate(str(user.pk))
        else:
            self.auth_timer = asyncio.create_task(self.authentication_timeout())

    async def authentication_timeout(self):
        try:
            await asyncio.sleep(10)
            if not self.authenticated:
                await self.close(code=4401)
        except asyncio.CancelledError:
            return

    @database_sync_to_async
    def active_user(self, user_id):
        return get_user_model().objects.filter(pk=user_id, is_active=True).exists()

    @database_sync_to_async
    def verify(self, content):
        if isinstance(content.get("token"), str):
            token = JWTAuthentication().get_validated_token(content["token"])
            user = JWTAuthentication().get_user(token)
            return str(user.pk), int(token["exp"])
        if isinstance(content.get("ticket"), str):
            payload = signing.loads(content["ticket"], salt=WS_TICKET_SALT, max_age=60)
            user = get_user_model().objects.get(pk=payload["user_id"], is_active=True)
            return str(user.pk), None
        raise ValueError("Credentials required")

    @database_sync_to_async
    def role_for(self, user_id):
        user = get_user_model().objects.get(pk=user_id, is_active=True)
        return user.role

    async def activate(self, user_id, expiry=None):
        if self.authenticated:
            return
        self.user_id = user_id
        self.role = await self.role_for(user_id)
        self.authenticated = True
        if self.auth_timer:
            self.auth_timer.cancel()
        groups = [f"notifications.{user_id}"]
        if self.role in ("staff", "admin"):
            groups.append("staff_users")
        for group in groups:
            await self.channel_layer.group_add(group, self.channel_name)
            self.joined.append(group)
        await self.send_json({"type": "ready", "user_id": user_id, "role": self.role})
        if expiry is not None:
            self.expiry_task = asyncio.create_task(self.disconnect_at_expiry(expiry))

    async def disconnect_at_expiry(self, expiry):
        try:
            delay = max(0, expiry - datetime.now(timezone.utc).timestamp())
            await asyncio.sleep(delay)
            await self.close(code=4401)
        except asyncio.CancelledError:
            return

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            await self.close(code=4401)
            return
        if self.authenticated:
            if content.get("type") == "ping":
                await self.send_json({"type": "pong"})
            return
        try:
            user_id, expiry = await self.verify(content)
            await self.activate(user_id, expiry)
        except (InvalidToken, TokenError, AuthenticationFailed, signing.BadSignature, ValueError, KeyError,
                TypeError, get_user_model().DoesNotExist):
            await self.close(code=4401)

    @database_sync_to_async
    def authorized_for_event(self, payload):
        user = get_user_model().objects.filter(pk=self.user_id, is_active=True).first()
        if not user:
            return False
        if self.role in ("staff", "admin"):
            return user.role in ("staff", "admin")
        if user.role != "student":
            return False
        if payload.get("type", "").startswith("notification."):
            from .models import Notification
            return Notification.objects.filter(pk=payload.get("notification_id"), user_id=user).exists()
        submission_id = payload.get("submission_id")
        if not submission_id:
            return False
        from submissions.models import Submission
        from submissions.visibility import can_read_submission
        submission = Submission.objects.filter(pk=submission_id).first()
        return bool(submission and can_read_submission(user, submission))

    async def notification_changed(self, event):
        if not self.authenticated or not await self.active_user(self.user_id):
            await self.close(code=4401)
            return
        await self.send_json({"type": "notification.changed", "id": event["id"]})

    async def realtime_event(self, event):
        if not self.authenticated:
            return
        if not await self.active_user(self.user_id):
            await self.close(code=4401)
            return
        if not await self.authorized_for_event(event["payload"]):
            # Do not leak events from stale memberships or other users.
            return
        await self.send_json(event["payload"])

    async def disconnect(self, code):
        if self.auth_timer:
            self.auth_timer.cancel()
        if self.expiry_task:
            self.expiry_task.cancel()
        for group in self.joined:
            await self.channel_layer.group_discard(group, self.channel_name)
