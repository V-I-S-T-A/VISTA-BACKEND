from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = None
        await self.accept()

    async def receive_json(self, content, **kwargs):
        if self.user is not None:
            return

        token = content.get("token") if isinstance(content, dict) else None
        try:
            self.user = await self._get_user(token)
        except (InvalidToken, TokenError, TypeError, ValueError):
            await self.close(code=4401)
            return

        if self.user is None or not self.user.is_active:
            await self.close(code=4401)
            return

        self.group_name = f"notifications.{self.user.pk}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.send_json({"type": "ready", "user_id": str(self.user.pk), "role": self.user.role})

    async def disconnect(self, close_code):
        if self.user is not None:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification_changed(self, event):
        payload = {"type": event.get("event_type", "notification.changed"), "id": event["id"]}
        if event.get("review_log_id"):
            payload["review_log_id"] = event["review_log_id"]
        await self.send_json(payload)

    @database_sync_to_async
    def _get_user(self, raw_token):
        if not raw_token:
            raise InvalidToken("Missing access token")
        token = AccessToken(raw_token)
        user_id = token.get("user_id")
        if not user_id:
            raise InvalidToken("Token has no user id")
        from django.contrib.auth import get_user_model

        return get_user_model().objects.filter(pk=user_id).first()
