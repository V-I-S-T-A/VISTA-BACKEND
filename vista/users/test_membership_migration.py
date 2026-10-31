from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MembershipMigrationTests(TransactionTestCase):
    def test_legacy_dates_stay_unknown_and_original_remarks_survive(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [("users", "0006_user_phone_number"), ("review_logs", "0003_reviewlog_attachment_change"),
                  ("submissions", "0003_submission_priority_escalation")]
        try:
            executor.migrate(before)
            apps = executor.loader.project_state(before).apps
            org = apps.get_model("organizations", "Organization").objects.create(name="Legacy A", acronym="LEG")
            user = apps.get_model("users", "User").objects.create(email="legacy@example.test", first_name="Legacy", last_name="Student", org_id=org)
            submission = apps.get_model("submissions", "Submission").objects.create(title="Keep entry", description="Keep description", submitted_by=user, org_id=org)
            log = apps.get_model("review_logs", "ReviewLog").objects.create(submission_id=submission, changed_by=user, remarks_text="Keep original remarks", old_status="pending", new_status="pending")
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            apps = executor.loader.project_state(latest).apps
            migrated = apps.get_model("users", "User").objects.get(pk=user.pk)
            self.assertIsNone(migrated.org_joined_at)
            self.assertEqual(migrated.org_id_id, org.pk)
            self.assertFalse(apps.get_model("users", "OrganizationMembershipAudit").objects.exists())
            self.assertEqual(apps.get_model("review_logs", "ReviewLog").objects.get(pk=log.pk).remarks_text, "Keep original remarks")
            self.assertEqual(apps.get_model("review_logs", "ReviewReply").objects.count(), 0)
        finally:
            MigrationExecutor(connection).migrate(latest)
