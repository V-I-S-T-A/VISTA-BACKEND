from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from users.models import User
from submissions.models import Submission
from review_logs.models import ReviewLog
from audit_logs.models import AuditLog
from audit_logs.utility import log_create, log_login, log_status_change


class AuditLogScopingTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create users
        self.admin = User.objects.create_user(
            email="admin@vista.edu",
            first_name="Admin",
            last_name="User",
            password="Password123!",
            role="admin"
        )

        self.staff = User.objects.create_user(
            email="staff@vista.edu",
            first_name="Staff",
            last_name="User",
            password="Password123!",
            role="staff"
        )

        self.student1 = User.objects.create_user(
            email="student1@vista.edu",
            first_name="Student",
            last_name="One",
            password="Password123!",
            role="student"
        )

        self.student2 = User.objects.create_user(
            email="student2@vista.edu",
            first_name="Student",
            last_name="Two",
            password="Password123!",
            role="student"
        )

        # Create submissions
        self.sub1 = Submission.objects.create(
            title="Student 1 Proposal",
            description="Test proposal",
            submitted_by=self.student1,
            status=Submission.STATUS_PENDING
        )

        self.sub2 = Submission.objects.create(
            title="Student 2 Proposal",
            description="Test proposal 2",
            submitted_by=self.student2,
            status=Submission.STATUS_PENDING
        )

        # Audit log entries
        # 1. Admin login log
        log_login(self.admin)

        # 2. Student 1 login log
        log_login(self.student1)

        # 3. Student 2 login log
        log_login(self.student2)

        # 4. Staff updates status of Student 1 submission
        log_status_change(
            user=self.staff,
            table_name="tbl_Submissions",
            record_id=self.sub1.submission_id,
            old_status="pending",
            new_status="under_review"
        )
        ReviewLog.objects.create(
            submission_id=self.sub1,
            changed_by=self.staff,
            remarks_text="Reviewed",
            old_status="pending",
            new_status="under_review"
        )

    def test_admin_can_see_all_logs(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/api/audit-logs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        # Admin sees all 4 logs
        self.assertEqual(len(results), 4)

    def test_student1_can_see_only_related_logs(self):
        self.client.force_authenticate(user=self.student1)
        response = self.client.get("/api/audit-logs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        # Student 1 sees: their own login + staff status change on sub1
        self.assertEqual(len(results), 2)
        log_ids = [item["audit_id"] for item in results]
        # Admin and Student2 login logs should not be present
        for item in results:
            self.assertIn(
                item["action"],
                ["login", "status_change"]
            )

    def test_staff_can_see_staff_and_reviewed_student_logs(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get("/api/audit-logs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        # Staff sees: status change log (performed by staff) + Student 1 login log (reviewed student)
        self.assertEqual(len(results), 2)
