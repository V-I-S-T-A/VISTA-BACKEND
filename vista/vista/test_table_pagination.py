from datetime import datetime, timezone as dt_timezone

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from audit_logs.models import AuditLog
from audit_logs.views import AuditLogViewSet
from organizations.models import Organization
from submissions.models import Submission
from users.models import User
from users.views import UserViewSet


class TablePaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="A long organization name", acronym="LONG")
        cls.admin = User.objects.create_user(email="admin@example.test", first_name="Admin", last_name="User", role="admin")
        User.objects.bulk_create([
            User(email=f"person{i}@example.test", first_name=f"Person {i}", last_name="Surname",
                 org_id=cls.org, role="staff" if i % 3 == 0 else "student", is_active=i % 4 != 0)
            for i in range(121)
        ])
        cls.staff = User.objects.get(email="person0@example.test")
        cls.student = User.objects.get(email="person1@example.test")
        AuditLog.objects.bulk_create([
            AuditLog(user_id=user, action="create" if i % 2 == 0 else "update",
                     table_name="tbl_Users", changes={"large_payload": "x" * 10000})
            for i, user in enumerate(User.objects.exclude(role="admin").order_by("email"))
        ])
        AuditLog.objects.create(user_id=cls.admin, action="login", table_name="tbl_Users")
        AuditLog.objects.create(user_id=None, action="create", table_name="tbl_System")
        cls.submission = Submission.objects.create(title="Student submission", submitted_by=cls.student)
        cls.related_log = AuditLog.objects.create(user_id=cls.staff, action="status_change", table_name="tbl_Submissions",
                                                changes={"record_id": str(cls.submission.pk)})
        # Exercise deterministic tie-breaking rather than relying on timestamp resolution.
        User.objects.update(created_at=timezone.now())
        AuditLog.objects.update(performed_at=datetime(2026, 10, 24, 12, tzinfo=dt_timezone.utc))

    def users(self, user=None, action="list", **params):
        request = APIRequestFactory().get("/users/", {"exclude_admin": "true", **params})
        force_authenticate(request, user=user or self.admin)
        return UserViewSet.as_view({"get": action})(request)

    def logs(self, user=None, audit_id=None, **params):
        request = APIRequestFactory().get("/audit-logs/", params)
        force_authenticate(request, user=user or self.admin)
        return AuditLogViewSet.as_view({"get": "retrieve" if audit_id else "list"})(
            request, **({"audit_id": audit_id} if audit_id else {})
        )

    def test_user_summary_is_exact_above_api_page_cap_in_one_query(self):
        with self.assertNumQueries(1):
            response = self.users(action="summary")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"total": 121, "staff": 41, "students": 80, "inactive": 31})

    def test_summary_respects_filters_and_rejects_students(self):
        response = self.users(action="summary", role="staff", is_active="false")
        self.assertEqual(response.data, {"total": 11, "staff": 11, "students": 0, "inactive": 11})
        self.assertEqual(self.users(user=self.student, action="summary").status_code, 403)

    def test_users_reach_all_pages_without_duplicates_or_n_plus_one_queries(self):
        seen = set()
        for page in range(1, 17):
            with self.assertNumQueries(2):
                response = self.users(page=page, page_size=8)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["count"], 121)
            self.assertEqual(len(response.data["results"]), 8 if page < 16 else 1)
            ids = {row["user_id"] for row in response.data["results"]}
            self.assertFalse(seen & ids)
            seen |= ids
        self.assertEqual(len(seen), 121)

    def test_user_filters_apply_before_pagination(self):
        response = self.users(page=2, page_size=8, role="staff", is_active="false")
        self.assertEqual(response.data["count"], 11)
        self.assertEqual(len(response.data["results"]), 3)
        self.assertTrue(all(row["role"] == "staff" and not row["is_active"] for row in response.data["results"]))

    def test_compact_audit_pages_use_two_queries_and_omit_large_changes(self):
        seen = set()
        for page in range(1, 17):
            with CaptureQueriesContext(connection) as queries:
                response = self.logs(page=page, page_size=8, compact="true")
            self.assertEqual(len(queries), 2)
            self.assertNotIn('"changes"', queries[-1]["sql"])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["count"], 124)
            self.assertEqual(len(response.data["results"]), 8 if page < 16 else 4)
            self.assertTrue(all("changes" not in row for row in response.data["results"]))
            ids = {row["audit_id"] for row in response.data["results"]}
            self.assertFalse(seen & ids)
            seen |= ids
        self.assertEqual(len(seen), 124)

    def test_detail_retains_changes_and_uses_one_query(self):
        log = AuditLog.objects.filter(changes__has_key="large_payload").first()
        with self.assertNumQueries(1):
            response = self.logs(audit_id=log.audit_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["changes"], log.changes)

    def test_existing_audit_list_clients_still_receive_changes(self):
        response = self.logs(page_size=8)
        self.assertTrue(all("changes" in row for row in response.data["results"]))

    def test_audit_full_name_action_and_id_search_cover_the_whole_dataset(self):
        target = User.objects.get(email="person120@example.test")
        log = AuditLog.objects.get(user_id=target)
        for query in ("Person 120 Surname", str(log.audit_id)[:8]):
            with self.subTest(query=query):
                response = self.logs(query=query, compact="true", page_size=8)
                self.assertEqual(response.data["count"], 1)
                self.assertEqual(str(response.data["results"][0]["audit_id"]), str(log.audit_id))
        response = self.logs(query="status_change", compact="true", page_size=8)
        self.assertEqual(response.data["count"], 1)

    def test_date_filter_is_half_open_at_local_day_boundaries(self):
        # A UTC+08 local day includes exactly [Oct 23 16:00Z, Oct 24 16:00Z).
        for hour in (15, 16):
            log = AuditLog.objects.create(action="create", table_name="date_test")
            AuditLog.objects.filter(pk=log.pk).update(performed_at=datetime(2026, 10, 24, hour, tzinfo=dt_timezone.utc))
        response = self.logs(table_name="date_test", performed_after="2026-10-24T00:00:00+08:00",
                             performed_until="2026-10-25T00:00:00+08:00", compact="true")
        self.assertEqual(response.data["count"], 1)

    def test_staff_and_student_log_scopes_remain_enforced(self):
        response = self.logs(user=self.staff, compact="true", page_size=8)
        self.assertEqual(response.data["count"], 42)
        self.assertFalse(any(row["action"] in ("login", "logout") for row in response.data["results"]))
        response = self.logs(user=self.student, compact="true", page_size=8)
        self.assertEqual(response.data["count"], 2)
        self.assertIn(str(self.related_log.pk), {str(row["audit_id"]) for row in response.data["results"]})
        unrelated = AuditLog.objects.filter(user_id=self.admin).first()
        self.assertEqual(self.logs(user=self.student, audit_id=unrelated.pk).status_code, 404)
