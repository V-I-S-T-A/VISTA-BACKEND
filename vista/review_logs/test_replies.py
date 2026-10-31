import uuid
from datetime import timedelta
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from notifications.models import Notification
from organizations.models import Organization
from submissions.models import Submission
from users.models import User
from .models import ReviewLog, ReviewReply, REPLY_MAX_LENGTH


class ReviewReplyTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Organization A", acronym="A")
        self.owner = self.user("Alice", self.org)
        self.peer = self.user("Bob", self.org)
        self.outsider = self.user("Carol")
        self.staff = self.user("Staff", role="staff")
        self.admin = self.user("Admin", role="admin")
        self.entry = Submission.objects.create(title="Threaded entry", submitted_by=self.owner, org_id=self.org, status="approved")
        self.log = ReviewLog.objects.create(submission_id=self.entry, changed_by=self.staff, remarks_text="Please clarify the date.", old_status="under_review", new_status="approved")
        self.other_log = ReviewLog.objects.create(submission_id=self.entry, changed_by=self.staff, remarks_text="Second remark", old_status="approved", new_status="approved")
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def user(self, name, org=None, role="student"):
        return User.objects.create_user(email=f"{name}@example.test", first_name=name, last_name="Test", org_id=org, role=role, image_url=f"https://example.test/{name}.webp")

    def path(self, log=None):
        return f"/api/review-logs/{(log or self.log).pk}/replies/"

    def post(self, message="The date is correct.", **extra):
        return self.client.post(self.path(), {"message": message, "client_request_id": str(uuid.uuid4()), **extra}, format="json")

    def test_owner_staff_followup_persists_with_identity_and_exact_parent(self):
        response = self.post(author=str(self.staff.pk))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["author"], self.owner.pk)
        self.assertEqual(response.data["author_name"], "Alice Test")
        self.assertEqual(response.data["author_image_url"], self.owner.image_url)
        reply_id = response.data["reply_id"]
        self.client.force_authenticate(self.staff)
        response = self.post("Thank you.", parent_reply=str(reply_id))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["reply_to_name"], "Alice Test")
        rows = self.client.get(self.path()).data["results"]
        self.assertEqual([row["message"] for row in rows], ["The date is correct.", "Thank you."])
        self.assertEqual(str(rows[1]["parent_reply"]), reply_id)
        self.assertEqual(self.client.get(self.path(self.other_log)).data["count"], 0)
        self.assertEqual(self.client.get(f"/api/review-logs/{self.log.pk}/").data["reply_count"], 2)

    def test_eligible_peer_reads_but_cannot_reply_and_guessed_ids_are_hidden(self):
        self.post()
        self.client.force_authenticate(self.peer)
        self.assertEqual(self.client.get(self.path()).data["count"], 1)
        self.assertFalse(self.client.get(f"/api/review-logs/{self.log.pk}/").data["can_reply"])
        self.assertEqual(self.post().status_code, 403)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(self.path()).status_code, 404)
        self.assertEqual(self.post().status_code, 404)

    def test_unknown_dates_old_entries_and_lost_membership_hide_threads(self):
        self.client.force_authenticate(self.peer)
        User.objects.filter(pk=self.peer.pk).update(org_joined_at=None)
        self.peer.refresh_from_db()
        self.assertEqual(self.client.get(self.path()).status_code, 404)
        User.objects.filter(pk=self.peer.pk).update(org_joined_at=timezone.now() + timedelta(seconds=1))
        self.peer.refresh_from_db()
        self.assertEqual(self.client.get(self.path()).status_code, 404)
        self.peer.org_id = None
        self.peer.save(update_fields=["org_id"])
        self.assertEqual(self.client.get(self.path()).status_code, 404)

    def test_owner_after_leaving_and_admin_can_reply_regardless_of_status(self):
        self.owner.org_id = None
        self.owner.save(update_fields=["org_id"])
        for state in dict(Submission.STATUS_CHOICES):
            Submission.objects.filter(pk=self.entry.pk).update(status=state)
            self.assertEqual(self.post(state).status_code, 201)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.post("Admin response").status_code, 201)

    def test_cross_thread_parent_blank_long_messages_and_missing_request_id_rejected(self):
        parent = ReviewReply.objects.create(review_log=self.other_log, author=self.staff, message="Other thread", client_request_id=uuid.uuid4())
        self.assertEqual(self.post(parent_reply=str(parent.pk)).status_code, 400)
        self.assertEqual(self.post(parent_reply=str(uuid.uuid4())).status_code, 400)
        for text in ("", " \n\t ", "x" * (REPLY_MAX_LENGTH + 1)):
            self.assertEqual(self.post(text).status_code, 400)
        self.assertEqual(self.client.post(self.path(), {"message": "No request ID"}, format="json").status_code, 400)
        self.assertEqual(self.post("😀" * REPLY_MAX_LENGTH).status_code, 201)

    def test_identical_retry_is_idempotent_conflicting_retry_is_rejected(self):
        request_id = str(uuid.uuid4())
        first = self.post("  Confirmed  ", client_request_id=request_id)
        second = self.post("Confirmed", client_request_id=request_id)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["reply_id"], second.data["reply_id"])
        self.assertEqual(self.post("Changed", client_request_id=request_id).status_code, 409)
        self.assertEqual(self.client.get(self.path()).data["count"], 1)

    @patch("integrations.tasks.upload_document_to_drive.delay")
    @patch("notifications.tasks.send_push.delay")
    @patch("submissions.serializers.send_status_change_email")
    def test_reply_has_no_status_history_email_or_drive_side_effects(self, email, push, drive):
        status, updated_at, count = self.entry.status, self.entry.updated_at, ReviewLog.objects.count()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.post("<script>alert('text')</script>").status_code, 201)
        fresh = self.client.get(f"/api/submissions/{self.entry.pk}/")
        self.assertEqual(fresh.data["status"], status)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.updated_at, updated_at)
        self.assertEqual(ReviewLog.objects.count(), count)
        self.log.refresh_from_db()
        self.assertEqual(self.log.remarks_text, "Please clarify the date.")
        # Verified: student reply creates exactly one targeted notification for the responsible staff reviewer
        self.assertEqual(Notification.objects.count(), 1)
        notif = Notification.objects.first()
        self.assertEqual(notif.user_id, self.staff)
        self.assertEqual(notif.actor, self.owner)
        self.assertEqual(notif.type, "review_reply_created")
        # Existing channels (email, drive) are untouched
        email.assert_not_called()
        drive.assert_not_called()

    def test_student_reply_creates_targeted_staff_notification_and_notification_api(self):
        # Alice (owner) posts a reply to Staff's remark
        res = self.post("The date is confirmed.")
        self.assertEqual(res.status_code, 201)

        # 1. Staff receives exactly one targeted in-app notification
        notifications = Notification.objects.filter(user_id=self.staff)
        self.assertEqual(notifications.count(), 1)
        notif = notifications.first()
        self.assertEqual(notif.type, "review_reply_created")
        self.assertEqual(notif.actor, self.owner)
        self.assertEqual(notif.submission_id, self.entry)
        self.assertIn("Alice Test replied to your remark", notif.message)
        self.assertIn("Threaded entry", notif.message)
        self.assertFalse(notif.is_read)

        # 2. Staff views notification list via existing API
        self.client.force_authenticate(self.staff)
        list_res = self.client.get("/api/notifications/")
        self.assertEqual(list_res.status_code, 200)
        self.assertEqual(list_res.data["unread_count"], 1)
        self.assertEqual(len(list_res.data["results"]), 1)
        item = list_res.data["results"][0]
        self.assertEqual(str(item["notification_id"]), str(notif.notification_id))
        self.assertEqual(str(item["submission_id"]), str(self.entry.submission_id))
        self.assertEqual(item["submission_title"], self.entry.title)
        self.assertEqual(item["type"], "review_reply_created")
        self.assertEqual(item["actor_name"], "Alice Test")
        self.assertFalse(item["is_read"])

        # 3. Staff checks unread-count endpoint
        count_res = self.client.get("/api/notifications/unread-count/")
        self.assertEqual(count_res.status_code, 200)
        self.assertEqual(count_res.data["unread_count"], 1)

        # 4. Staff marks notification as read
        read_res = self.client.post(f"/api/notifications/{notif.notification_id}/read/")
        self.assertEqual(read_res.status_code, 200)
        self.assertTrue(read_res.data["is_read"])
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

        # 5. Unread count becomes 0
        count_res2 = self.client.get("/api/notifications/unread-count/")
        self.assertEqual(count_res2.data["unread_count"], 0)

    def test_student_reply_notification_isolation_and_no_self_notification(self):
        other_staff = self.user("OtherStaff", role="staff")
        self.post("Checking isolation.")

        # Responsible staff receives it
        self.assertEqual(Notification.objects.filter(user_id=self.staff).count(), 1)
        # Other OSA staff member does NOT receive it
        self.assertEqual(Notification.objects.filter(user_id=other_staff).count(), 0)
        # Other student in the same organization does NOT receive it
        self.assertEqual(Notification.objects.filter(user_id=self.peer).count(), 0)
        # Reply author receives NO self-notification
        self.assertEqual(Notification.objects.filter(user_id=self.owner).count(), 0)

    def test_duplicate_client_request_id_retry_does_not_duplicate_notification(self):
        request_id = str(uuid.uuid4())
        res1 = self.post("Idempotent check", client_request_id=request_id)
        self.assertEqual(res1.status_code, 201)
        self.assertEqual(Notification.objects.filter(user_id=self.staff).count(), 1)

        # Retry with identical client_request_id
        res2 = self.post("Idempotent check", client_request_id=request_id)
        self.assertEqual(res2.status_code, 200)
        # Notification count MUST remain exactly 1
        self.assertEqual(Notification.objects.filter(user_id=self.staff).count(), 1)

    def test_staff_reply_does_not_create_staff_notification(self):
        self.client.force_authenticate(self.staff)
        res = self.post("Staff replying directly")
        self.assertEqual(res.status_code, 201)
        # No staff notification created when staff replies
        self.assertEqual(Notification.objects.count(), 0)

    def test_fallback_staff_resolution_when_log_changed_by_is_none(self):
        # Create a second staff user who made an earlier review
        prev_staff = self.user("PrevStaff", role="staff")
        ReviewLog.objects.create(
            submission_id=self.entry,
            changed_by=prev_staff,
            remarks_text="Initial review.",
            old_status="pending",
            new_status="under_review",
        )
        # Set the current log's changed_by to None (e.g. author removed)
        ReviewLog.objects.filter(pk=self.log.pk).update(changed_by=None)
        self.log.refresh_from_db()

        res = self.post("Reply to log with null changed_by")
        self.assertEqual(res.status_code, 201)
        # Falls back to prev_staff (the active staff reviewer on this submission)
        self.assertEqual(Notification.objects.filter(user_id=prev_staff).count(), 1)
        notif = Notification.objects.filter(user_id=prev_staff).first()
        self.assertEqual(notif.type, "review_reply_created")

    def test_pagination_stable_counts_and_no_edit_delete_operations(self):
        for index in range(23):
            ReviewReply.objects.create(review_log=self.log, author=self.owner, message=f"Reply {index}", client_request_id=uuid.uuid4())
        first = self.client.get(self.path(), {"page_size": 20})
        second = self.client.get(self.path(), {"page": 2, "page_size": 20})
        self.assertEqual(first.data["count"], 23)
        self.assertEqual(len(first.data["results"]), 20)
        self.assertEqual(len(second.data["results"]), 3)
        ids = [row["reply_id"] for page in (first, second) for row in page.data["results"]]
        self.assertEqual(len(set(ids)), 23)
        self.assertEqual(self.client.put(self.path(), {"message": "edit"}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(self.path()).status_code, 405)

    def test_no_remark_disallows_creation_but_old_history_remains_accessible(self):
        ReviewLog.objects.filter(pk=self.log.pk).update(remarks_text="", changed_at=timezone.now() - timedelta(days=2))
        self.assertEqual(self.post().status_code, 400)
        self.assertEqual(self.client.get(self.path()).status_code, 200)
        self.assertEqual(self.client.get(f"/api/review-logs/{self.log.pk}/").status_code, 200)

    def test_rollback_discards_reply_without_external_events(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.assertEqual(self.post().status_code, 201)
                raise RuntimeError("rollback")
        self.assertEqual(self.client.get(self.path()).data["count"], 0)
        self.assertFalse(Notification.objects.exists())

    def test_authorized_submission_deletion_is_not_blocked_by_followup_relationships(self):
        first = self.post().data
        self.post("Followup", parent_reply=first["reply_id"])
        self.entry.delete()
        self.assertFalse(ReviewReply.objects.exists())

    def test_reply_read_query_count_does_not_grow_with_page_size(self):
        parent = self.post().data
        for index in range(5):
            self.post(f"Followup {index}", parent_reply=parent["reply_id"])
        with self.assertNumQueries(3):
            response = self.client.get(self.path())
            self.assertEqual(len(response.data["results"]), 6)

    def test_removed_reviewer_keeps_original_remark_and_owner_thread_available(self):
        self.client.force_authenticate(self.staff)
        first = self.post("Retained staff response").data
        self.staff.delete()
        self.client.force_authenticate(self.owner)
        log = self.client.get(f"/api/review-logs/{self.log.pk}/")
        self.assertTrue(log.data["can_reply"])
        self.assertEqual(log.data["remarks_text"], "Please clarify the date.")
        self.assertEqual(self.post("Owner followup", parent_reply=first["reply_id"]).status_code, 201)
        rows = self.client.get(self.path()).data["results"]
        self.assertIsNone(rows[0]["author"])
        self.assertEqual(rows[0]["author_name"], "Former user")
