import asyncio
import time
import uuid
from datetime import datetime, timezone

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from rest_framework_simplejwt.authentication import JWTAuthentication


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = None
        self.user_group = None
        self.staff_group = None
        self.auth_timer = None
        self.expiry_timer = None

        scope_user = self.scope.get("user")
        if scope_user and scope_user.is_authenticated:
            await self.accept()
            await self._setup_authenticated_user(scope_user)
            return

        await self.accept()
        loop = asyncio.get_running_loop()
        self.auth_timer = loop.call_later(
            10,
            lambda: asyncio.create_task(self._close_unauthenticated()),
        )

    async def _close_unauthenticated(self):
        if not self.user:
            await self.close(code=4401)

    async def _close_expired(self):
        await self.close(code=4401)

    @database_sync_to_async
    def authenticate_token(self, raw_token):
        if not raw_token or not isinstance(raw_token, str):
            raise ValueError("Token is required.")

        # Accept short-lived signed WebSocket tickets.
        from django.core import signing

        try:
            data = signing.loads(raw_token, salt="ws-ticket", max_age=120)
            user_id = data.get("user_id")

            from users.models import User

            user = User.objects.get(pk=user_id, is_active=True)
            return str(user.pk), user.role, data.get("exp")
        except Exception:
            pass

        # Otherwise authenticate the normal JWT access token.
        auth = JWTAuthentication()
        validated_token = auth.get_validated_token(raw_token)
        user = auth.get_user(validated_token)

        if not user or not user.is_active:
            raise ValueError("Inactive or invalid user.")

        return str(user.pk), user.role, validated_token.get("exp")

    async def _setup_authenticated_user(self, user_or_pk, role=None, expiry=None):
        if hasattr(user_or_pk, "pk"):
            user_pk = str(user_or_pk.pk)
            role = user_or_pk.role
        else:
            user_pk = str(user_or_pk)

        self.user = user_or_pk
        self.user_group = f"notifications.{user_pk}"
        await self.channel_layer.group_add(self.user_group, self.channel_name)

        if role in ("staff", "admin"):
            self.staff_group = "staff_users"
            await self.channel_layer.group_add(self.staff_group, self.channel_name)

        if expiry:
            remaining = max(0, expiry - time.time())
            loop = asyncio.get_running_loop()
            self.expiry_timer = loop.call_later(
                remaining,
                lambda: asyncio.create_task(self._close_expired()),
            )

        await self.send_json({
            "type": "ready",
            "user_id": user_pk,
            "role": role,
        })

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            await self.close(code=4401)
            return

        if content.get("type") == "ping":
            if not self.user:
                await self.close(code=4401)
                return
            await self.send_json({"type": "pong"})
            return

        if self.user:
            return

        token = content.get("token") or content.get("ticket")
        if not token:
            await self.close(code=4401)
            return

        try:
            user_pk, role, expiry = await self.authenticate_token(token)
        except Exception:
            await self.close(code=4401)
            return

        if self.auth_timer:
            self.auth_timer.cancel()
            self.auth_timer = None

        await self._setup_authenticated_user(user_pk, role, expiry)

    async def realtime_event(self, event):
        await self.send_json(event["payload"])

    async def notification_changed(self, event):
        # Preserve the existing payload format for legacy and test events.
        if "payload" in event:
            await self.send_json(event["payload"])
            return

        event_type = event.get("event_type", "notification.changed")
        payload = {
            "version": 1,
            "event_id": str(uuid.uuid4()),
            "type": event_type,
            "id": event.get("id"),
            "occurred_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

        if event_type == "notification.changed":
            payload["notification_id"] = event.get(
                "notification_id",
                event.get("id"),
            )

        if event.get("review_log_id"):
            payload["review_log_id"] = event["review_log_id"]

        await self.send_json(payload)

    async def disconnect(self, code):
        if self.auth_timer:
            self.auth_timer.cancel()
            self.auth_timer = None

        if self.expiry_timer:
            self.expiry_timer.cancel()
            self.expiry_timer = None

        if self.user_group:
            await self.channel_layer.group_discard(
                self.user_group,
                self.channel_name,
            )

        if self.staff_group:
            await self.channel_layer.group_discard(
                self.staff_group,
                self.channel_name,
            )