"""Explicit membership dates; all mutations are read back through a fresh API request."""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from audit_logs.utility import log_status_change
from documents.models import Document
from organizations.models import Organization
from review_logs.models import ReviewLog
from users.models import User, OrganizationMembershipAudit
from .models import Submission


class OrganizationJoiningTests(TestCase):
    def setUp(self):
        self.joined = timezone.now() - timedelta(days=10)
        self.org_a = Organization.objects.create(name="Organization A", acronym="A")
        self.org_b = Organization.objects.create(name="Organization B", acronym="B")
        self.alice = self.user("Alice", self.org_a)
        self.bob = self.user("Bob", self.org_a)
        self.carol = self.user("Carol", self.org_b)
        self.admin = self.user("Admin", role="admin")
        self.staff = self.user("Staff", role="staff")
        self.before = self.submission(self.bob, self.org_a, self.joined - timedelta(microseconds=1))
        self.equal = self.submission(self.bob, self.org_a, self.joined)
        self.after = self.submission(self.bob, self.org_a, self.joined + timedelta(days=1))
        self.own = self.submission(self.alice, self.org_a, self.joined - timedelta(days=1))
        self.foreign = self.submission(self.carol, self.org_b, self.joined + timedelta(days=1))
        self.client = APIClient()
        self.client.force_authenticate(self.alice)

    def user(self, name, org=None, role="student"):
        user = User.objects.create_user(email=f"{name}@example.test", first_name=name, last_name="Test", org_id=org, role=role)
        # Explicit verified fixture dates, never a runtime backfill.
        User.objects.filter(pk=user.pk).update(org_joined_at=self.joined if org else None)
        user.refresh_from_db()
        return user

    def submission(self, owner, org, when):
        obj = Submission.objects.create(submitted_by=owner, org_id=org, title="Dated entry", status="pending")
        Submission.objects.filter(pk=obj.pk).update(submitted_at=when)
        obj.refresh_from_db()
        return obj

    def detail(self, obj):
        return self.client.get(f"/api/submissions/{obj.pk}/")

    def visible_ids(self):
        response = self.client.get("/api/submissions/", {"page_size": 100})
        self.assertEqual(response.status_code, 200, response.data)
        ids = [row["submission_id"] for row in response.data["results"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(response.data["count"], len(ids))
        return set(ids)

    def test_cutoff_is_inclusive_and_owner_union_does_not_duplicate(self):
        self.assertEqual(self.visible_ids(), {str(obj.pk) for obj in (self.equal, self.after, self.own)})
        self.assertEqual(self.detail(self.before).status_code, 404)
        self.assertEqual(self.detail(self.equal).status_code, 200)
        response = self.client.get("/api/submissions/", {"page_size": 1, "page": 2})
        self.assertEqual(response.data["count"], 3)

    def test_unknown_date_and_null_org_are_owner_only(self):
        User.objects.filter(pk=self.alice.pk).update(org_joined_at=None)
        self.alice.refresh_from_db()
        self.assertEqual(self.visible_ids(), {str(self.own.pk)})
        self.alice.org_id = None
        self.alice.save(update_fields=["org_id"])
        null_entry = self.submission(self.bob, None, timezone.now())
        self.assertEqual(self.visible_ids(), {str(self.own.pk)})
        self.assertEqual(self.detail(null_entry).status_code, 404)

    def test_transfer_leave_rejoin_use_latest_period_and_preserve_stored_org(self):
        self.alice.org_id = self.org_b
        self.alice.save(update_fields=["org_id"])
        transferred_at = self.alice.org_joined_at
        self.assertGreater(transferred_at, self.joined)
        fresh_b = self.submission(self.carol, self.org_b, transferred_at)
        self.assertEqual(self.visible_ids(), {str(self.own.pk), str(fresh_b.pk)})
        self.assertEqual(self.detail(self.after).status_code, 404)
        self.assertEqual(self.detail(self.foreign).status_code, 404)
        self.own.refresh_from_db()
        self.assertEqual(self.own.org_id_id, self.org_a.pk)
        self.alice.org_id = None
        self.alice.save(update_fields=["org_id"])
        self.assertIsNone(self.alice.org_joined_at)
        self.assertEqual(self.visible_ids(), {str(self.own.pk)})
        self.alice.org_id = self.org_a
        self.alice.save(update_fields=["org_id"])
        self.assertGreater(self.alice.org_joined_at, transferred_at)
        fresh_a = self.submission(self.bob, self.org_a, self.alice.org_joined_at)
        self.assertEqual(self.visible_ids(), {str(self.own.pk), str(fresh_a.pk)})
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.detail(self.own).status_code, 404)  # Alice's older entry predates Bob's membership.
        User.objects.filter(pk=self.bob.pk).update(org_joined_at=self.own.submitted_at)
        self.bob.refresh_from_db()
        self.assertEqual(self.detail(self.own).status_code, 200)  # Stored Organization A survives Alice's transfer.

    def test_profile_same_assignment_and_direct_date_attempt_preserve_join_time(self):
        before = self.alice.org_joined_at
        count = self.alice.membership_audits.count()
        response = self.client.patch("/api/auth/me/", {"first_name": "Alice updated", "org_id": str(self.org_a.pk),
                   "org_joined_at": "1900-01-01T00:00:00Z"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.alice.refresh_from_db()
        fresh = self.client.get("/api/auth/me/")
        self.assertEqual(fresh.data["first_name"], "Alice updated")
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.org_joined_at, before)
        self.assertEqual(self.alice.membership_audits.count(), count)

    def test_student_cannot_self_transfer_through_either_profile_path(self):
        for path in ("/api/auth/me/", f"/api/users/{self.alice.pk}/"):
            response = self.client.patch(path, {"org_id": str(self.org_b.pk)}, format="json")
            self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.client.get("/api/auth/me/").data["org_id"], self.org_a.pk)

    def test_admin_assignment_is_persisted_timestamped_and_audited(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(f"/api/users/{self.alice.pk}/", {"org_id": str(self.org_b.pk)}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        fresh = self.client.get(f"/api/users/{self.alice.pk}/")
        self.assertEqual(fresh.data["org_id"], self.org_b.pk)
        self.alice.refresh_from_db()
        self.assertGreater(self.alice.org_joined_at, self.joined)
        event = self.alice.membership_audits.first()
        self.assertEqual(event.actor_id, self.admin.pk)
        self.assertEqual(event.previous_org_id, self.org_a.pk)
        self.assertEqual(event.org_id_value, self.org_b.pk)

    def test_verified_correction_requires_admin_evidence_timezone_and_current_org(self):
        path = f"/api/users/{self.alice.pk}/verify-organization-joining/"
        payload = {"org_id": str(self.org_a.pk), "expected_joined_at": self.alice.org_joined_at.isoformat(),
                   "joined_at": (self.joined - timedelta(days=2)).isoformat(), "evidence": "Membership register 2026, signed entry 42"}
        for user in (self.alice, self.staff):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.post(path, payload, format="json").status_code, 403)
        self.client.force_authenticate(self.admin)
        for invalid in ({"evidence": " "}, {"joined_at": "2026-01-01T10:00:00"},
                        {"joined_at": (timezone.now() + timedelta(days=1)).isoformat()}):
            self.assertEqual(self.client.post(path, {**payload, **invalid}, format="json").status_code, 400)
        self.assertEqual(self.client.post(path, {**payload, "org_id": str(self.org_b.pk)}, format="json").status_code, 409)
        response = self.client.post(path, payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.client.get(f"/api/users/{self.alice.pk}/").data["org_joined_at"], response.data["org_joined_at"])
        event = self.alice.membership_audits.first()
        self.assertEqual(event.evidence, payload["evidence"])
        self.assertEqual(event.reason, "verification")
        count = self.alice.membership_audits.count()
        self.client.post(path, payload, format="json")
        self.assertEqual(self.alice.membership_audits.count(), count)

    def test_guessed_history_audit_and_private_document_ids_follow_read_boundary(self):
        old_log = ReviewLog.objects.create(submission_id=self.before, changed_by=self.staff,
                    remarks_text="Private old remark", old_status="pending", new_status="pending")
        new_log = ReviewLog.objects.create(submission_id=self.after, changed_by=self.staff,
                    remarks_text="Readable new remark", old_status="pending", new_status="pending")
        self.assertEqual(self.client.get(f"/api/review-logs/{old_log.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/review-logs/{new_log.pk}/").status_code, 200)
        log_status_change(self.staff, "tbl_Submissions", self.before.pk, "pending", "approved")
        log_status_change(self.staff, "tbl_Submissions", self.after.pk, "pending", "approved")
        audit = self.client.get("/api/audit-logs/").data["results"]
        self.assertEqual(len(audit), 1)
        document = Document.objects.create(submission_id=self.after, file_name="staff.pdf", file_url="https://example.test/private.pdf", mime_type="application/pdf", file_size_kb=1)
        self.assertEqual(self.detail(self.after).data["documents"], [])
        for method, suffix, payload in (("get", "", None), ("patch", "", {"file_name": "changed"}), ("delete", "", None)):
            response = getattr(self.client, method)(f"/api/documents/{document.pk}/{suffix}", payload, format="json")
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get("/api/submissions/statistics/").status_code, 403)

    def test_peer_writes_fail_and_owner_pending_edit_survives_transfer(self):
        self.assertEqual(self.client.patch(f"/api/submissions/{self.after.pk}/", {"title": "No"}, format="json").status_code, 403)
        self.alice.org_id = self.org_b
        self.alice.save(update_fields=["org_id"])
        response = self.client.patch(f"/api/submissions/{self.own.pk}/", {"title": "Owner revision"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.detail(self.own).data["title"], "Owner revision")

    def test_stale_profile_serializer_does_not_revert_admin_transfer(self):
        from types import SimpleNamespace
        from users.serializers import UserUpdateSerializer
        serializer = UserUpdateSerializer(self.alice, data={"first_name": "Unrelated edit"}, partial=True,
                    context={"request": SimpleNamespace(user=self.alice)})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        transferred = User.objects.get(pk=self.alice.pk)
        transferred.org_id = self.org_b
        transferred.save(update_fields=["org_id"])
        serializer.save()
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.org_id_id, self.org_b.pk)
        self.assertEqual(self.alice.org_joined_at, transferred.org_joined_at)

    def test_stale_verified_correction_cannot_restore_an_earlier_membership_period(self):
        self.client.force_authenticate(self.admin)
        payload = {"org_id": str(self.org_a.pk), "expected_joined_at": self.alice.org_joined_at.isoformat(),
                   "joined_at": self.joined.isoformat(), "evidence": "Earlier membership register"}
        self.alice.org_id = None
        self.alice.save(update_fields=["org_id"])
        self.alice.org_id = self.org_a
        self.alice.save(update_fields=["org_id"])
        self.assertEqual(self.client.post(f"/api/users/{self.alice.pk}/verify-organization-joining/", payload, format="json").status_code, 409)

    def test_prevalidated_unchanged_org_cannot_undo_a_concurrent_transfer(self):
        from types import SimpleNamespace
        from rest_framework.exceptions import ValidationError
        from users.serializers import UserUpdateSerializer
        serializer = UserUpdateSerializer(self.alice, data={"org_id": str(self.org_a.pk)}, partial=True,
                    context={"request": SimpleNamespace(user=self.alice)})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        transferred = User.objects.get(pk=self.alice.pk)
        transferred.org_id = self.org_b
        transferred.save(update_fields=["org_id"])
        with self.assertRaises(ValidationError):
            serializer.save()
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.org_id_id, self.org_b.pk)
