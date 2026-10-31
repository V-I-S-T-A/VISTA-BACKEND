import asyncio
import time
import uuid
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.core import signing
from django.db import transaction
from django.test import TestCase, override_settings
from users.models import User
from submissions.models import Submission
from review_logs.models import ReviewLog, ReviewReply
from notifications.models import Notification
from .consumers import NotificationConsumer
from .tasks import purge_expired_notifications
from .events import (
    EVENT_SUBMISSION_CREATED,
    EVENT_SUBMISSION_UPDATED,
    EVENT_REVIEW_LOG_CREATED,
    EVENT_REVIEW_REPLY_CREATED,
    EVENT_NOTIFICATION_CREATED,
    EVENT_NOTIFICATION_READ,
    broadcast_submission_created,
    broadcast_submission_updated,
    broadcast_review_log_created,
    broadcast_review_reply_created,
    broadcast_notification_created,
    broadcast_notification_read,
)


class RealtimeConsumerTests(IsolatedAsyncioTestCase):
    def setUp(self):
        config = override_settings(
            CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
            NOTIFICATIONS_PUSH_ENABLED=False,
        )
        config.enable()
        self.addCleanup(config.disable)
    async def test_invalid_auth_is_rejected(self):
        connection = WebsocketCommunicator(NotificationConsumer.as_asgi(), "/ws/notifications/")
        await connection.connect()
        with patch.object(NotificationConsumer, "authenticate_token", AsyncMock(side_effect=ValueError)):
            await connection.send_json_to({"token": "invalid"})
            response = await connection.receive_output()
            self.assertEqual(response["code"], 4401)
        await connection.disconnect()

    async def test_missing_token_is_rejected(self):
        connection = WebsocketCommunicator(NotificationConsumer.as_asgi(), "/ws/notifications/")
        await connection.connect()
        await connection.send_json_to({"other": "field"})
        response = await connection.receive_output()
        self.assertEqual(response["code"], 4401)
        await connection.disconnect()

    async def test_ping_pong_response(self):
        connection = WebsocketCommunicator(NotificationConsumer.as_asgi(), "/ws/notifications/")
        await connection.connect()
        await connection.send_json_to({"type": "ping"})
        response = await connection.receive_json_from()
        self.assertEqual(response.get("type"), "pong")
        await connection.disconnect()

    async def test_user_channel_is_isolated(self):
        connection = WebsocketCommunicator(NotificationConsumer.as_asgi(), "/ws/notifications/")
        await connection.connect()
        with patch.object(NotificationConsumer, "authenticate_token", AsyncMock(return_value=("user-a", "student", time.time() + 60))):
            await connection.send_json_to({"token": "test"})
            self.assertEqual((await connection.receive_json_from())["type"], "ready")

        layer = get_channel_layer()
        # Events sent to user-b must NOT reach user-a
        await layer.group_send("notifications.user-b", {"type": "notification.changed", "id": "private"})
        self.assertTrue(await connection.receive_nothing(timeout=0.05))

        # Events sent to user-a must reach user-a
        await layer.group_send("notifications.user-a", {"type": "notification.changed", "id": "own"})
        msg = await connection.receive_json_from()
        self.assertEqual(msg["id"], "own")
        await connection.disconnect()

    async def test_multiple_connections_per_user(self):
        conn1 = WebsocketCommunicator(NotificationConsumer.as_asgi(), "/ws/notifications/")
        conn2 = WebsocketCommunicator(NotificationConsumer.as_asgi(), "/ws/notifications/")
        await conn1.connect()
        await conn2.connect()

        with patch.object(NotificationConsumer, "authenticate_token", AsyncMock(return_value=("user-multi", "student", time.time() + 60))):
            await conn1.send_json_to({"token": "t1"})
            await conn2.send_json_to({"token": "t2"})
            self.assertEqual((await conn1.receive_json_from())["type"], "ready")
            self.assertEqual((await conn2.receive_json_from())["type"], "ready")

        layer = get_channel_layer()
        await layer.group_send("notifications.user-multi", {
            "type": "realtime.event",
            "payload": {"version": 1, "type": "notification.created", "notification_id": "notif-1"},
        })

        msg1 = await conn1.receive_json_from()
        msg2 = await conn2.receive_json_from()
        self.assertEqual(msg1["notification_id"], "notif-1")
        self.assertEqual(msg2["notification_id"], "notif-1")

        await conn1.disconnect()
        await conn2.disconnect()

    async def test_staff_users_group_membership(self):
        staff_conn = WebsocketCommunicator(NotificationConsumer.as_asgi(), "/ws/notifications/")
        student_conn = WebsocketCommunicator(NotificationConsumer.as_asgi(), "/ws/notifications/")
        await staff_conn.connect()
        await student_conn.connect()

        with patch.object(NotificationConsumer, "authenticate_token", AsyncMock(return_value=("staff-1", "staff", time.time() + 60))):
            await staff_conn.send_json_to({"token": "staff-tok"})
            self.assertEqual((await staff_conn.receive_json_from())["type"], "ready")

        with patch.object(NotificationConsumer, "authenticate_token", AsyncMock(return_value=("student-1", "student", time.time() + 60))):
            await student_conn.send_json_to({"token": "student-tok"})
            self.assertEqual((await student_conn.receive_json_from())["type"], "ready")

        layer = get_channel_layer()
        # Broadcast sent to staff_users should only reach staff
        await layer.group_send("staff_users", {
            "type": "realtime.event",
            "payload": {"version": 1, "type": "submission.created", "submission_id": "sub-123"},
        })

        self.assertEqual((await staff_conn.receive_json_from())["submission_id"], "sub-123")
        self.assertTrue(await student_conn.receive_nothing(timeout=0.05))

        await staff_conn.disconnect()
        await student_conn.disconnect()

    async def test_ticket_authentication_success(self):
        ticket = signing.dumps({"user_id": "test-uuid", "role": "student", "exp": time.time() + 60}, salt="ws-ticket")
        consumer = NotificationConsumer()
        with patch("users.models.User.objects.get") as mock_get:
            mock_user = User(pk="test-uuid", role="student", is_active=True)
            mock_get.return_value = mock_user
            user_id, role, exp = await consumer.authenticate_token(ticket)
            self.assertEqual(user_id, "test-uuid")
            self.assertEqual(role, "student")


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
    NOTIFICATIONS_PUSH_ENABLED=False,
)
class RealtimeBroadcastEventTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(email="staff-rt@example.com", first_name="Staff", last_name="User", role="staff")
        self.student = User.objects.create_user(email="student-rt@example.com", first_name="Student", last_name="User", role="student")
        self.other_student = User.objects.create_user(email="other-rt@example.com", first_name="Other", last_name="User", role="student")

    def test_submission_created_broadcast_reaches_staff_and_submitter_only(self):
        with patch("notifications.events.send_group_event") as mock_send:
            with self.captureOnCommitCallbacks(execute=True):
                sub = Submission.objects.create(title="RT Entry", submitted_by=self.student, status="under_review")

        # Must have sent to staff_users and the submitter
        target_groups = {call.args[0] for call in mock_send.call_args_list}
        self.assertIn("staff_users", target_groups)
        self.assertIn(f"notifications.{self.student.pk}", target_groups)
        self.assertNotIn(f"notifications.{self.other_student.pk}", target_groups)

    def test_review_reply_created_broadcast(self):
        sub = Submission.objects.create(title="RT Reply Entry", submitted_by=self.student, status="under_review")
        log = ReviewLog.objects.create(submission_id=sub, changed_by=self.staff, remarks_text="Remark", old_status="under_review", new_status="under_review")

        with patch("notifications.events.send_group_event") as mock_send:
            with self.captureOnCommitCallbacks(execute=True):
                reply = ReviewReply.objects.create(
                    review_log=log, author=self.student, message="Hello staff", client_request_id=uuid.uuid4()
                )

        target_groups = {call.args[0] for call in mock_send.call_args_list}
        self.assertIn("staff_users", target_groups)
        self.assertIn(f"notifications.{self.student.pk}", target_groups)
        self.assertNotIn(f"notifications.{self.other_student.pk}", target_groups)

        # Verify payload structure
        payloads = [call.args[1] for call in mock_send.call_args_list]
        reply_payload = next(p for p in payloads if p.get("type") == EVENT_REVIEW_REPLY_CREATED)
        self.assertEqual(reply_payload["submission_id"], str(sub.pk))
        self.assertEqual(reply_payload["review_log_id"], str(log.pk))
        self.assertEqual(reply_payload["reply_id"], str(reply.pk))
        self.assertEqual(reply_payload["version"], 1)

    def test_notification_creation_and_read_isolation(self):
        sub = Submission.objects.create(title="RT Notif Entry", submitted_by=self.student, status="under_review")

        # 1. Creation
        with patch("notifications.events.send_group_event") as mock_send:
            with self.captureOnCommitCallbacks(execute=True):
                notif = Notification.objects.create(
                    user_id=self.student, actor=self.staff, submission_id=sub,
                    type="submission_created", message="Entry received"
                )

        # Must only be sent to the recipient's group
        target_groups = [call.args[0] for call in mock_send.call_args_list]
        self.assertTrue(all(g == f"notifications.{self.student.pk}" for g in target_groups))

        # 2. Mark as read
        with patch("notifications.events.send_group_event") as mock_send_read:
            with self.captureOnCommitCallbacks(execute=True):
                notif.is_read = True
                notif.save(update_fields=["is_read"])

        target_groups_read = [call.args[0] for call in mock_send_read.call_args_list]
        self.assertTrue(all(g == f"notifications.{self.student.pk}" for g in target_groups_read))
        payload = mock_send_read.call_args_list[0].args[1]
        self.assertEqual(payload["type"], EVENT_NOTIFICATION_READ)
        self.assertEqual(payload["notification_id"], str(notif.pk))

    def test_rollback_does_not_broadcast_events(self):
        with patch("notifications.events.send_group_event") as mock_send:
            try:
                with transaction.atomic():
                    Submission.objects.create(title="Rolled back entry", submitted_by=self.student, status="under_review")
                    raise RuntimeError("Simulated transaction abort")
            except RuntimeError:
                pass

        # Since transaction was aborted and rolled back, on_commit callbacks must NOT execute
        mock_send.assert_not_called()


class RetentionTests(TestCase):
    def test_cleanup_targets_notification_rows_only(self):
        with patch("notifications.tasks.Notification.objects.filter") as query:
            query.return_value.delete.return_value = (2, {})
            self.assertEqual(purge_expired_notifications(), 2)
            self.assertIn("created_at__lt", query.call_args.kwargs)
            query.return_value.delete.assert_called_once()
