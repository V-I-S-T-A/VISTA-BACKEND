"""Organization sharing through the API used by both web and Android."""
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.core import mail
from rest_framework.test import APIClient

from audit_logs.utility import log_login, log_status_change
from documents.models import Document
from organizations.models import Organization
from notifications.models import Notification
from users.models import User
from .models import Submission


@override_settings(NOTIFICATIONS_PUSH_ENABLED=False,
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class OrganizationVisibilityTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Organization A', acronym='ORG-A')
        self.other_org = Organization.objects.create(name='Organization B', acronym='ORG-B')
        self.owner = self.user('owner', self.org)
        self.peer = self.user('peer', self.org)
        self.outsider = self.user('outsider', self.other_org)
        self.unassigned = self.user('unassigned')
        self.staff = self.user('staff', role='staff')
        self.entry = Submission.objects.create(title='Shared entry', submitted_by=self.owner,
                                               org_id=self.org, status='under_review', priority_escalation=True)
        self.foreign = Submission.objects.create(title='Private entry', submitted_by=self.outsider,
                                                 org_id=self.other_org, status='under_review')
        self.legacy = Submission.objects.create(title='Owner legacy', submitted_by=self.peer, status='pending')
        self.client = APIClient()
        self.client.force_authenticate(self.peer)

    def user(self, name, org=None, role='student'):
        return User.objects.create_user(email=f'{name}@example.test', first_name=name,
                                        last_name='Test', org_id=org, role=role)

    def rows(self, path, **params):
        response = self.client.get(path, params)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['results']

    def test_dashboard_tracker_counts_and_priority_include_peers_but_not_other_orgs(self):
        rows = self.rows('/api/submissions/')
        self.assertEqual({row['submission_id'] for row in rows}, {str(self.entry.pk), str(self.legacy.pk)})
        self.assertEqual(self.client.get('/api/submissions/', {'page_size': 1}).data['count'], 2)
        priority = self.rows('/api/submissions/', priority_escalation='true')
        self.assertEqual([row['submission_id'] for row in priority], [str(self.entry.pk)])
        self.assertEqual(self.rows('/api/submissions/', org_id=str(self.other_org.pk)), [])
        self.assertEqual(self.rows('/api/submissions/', submitted_by=str(self.outsider.pk)), [])

    def test_details_are_shared_but_student_attachments_stay_hidden(self):
        Document.objects.create(submission_id=self.entry, file_name='private.webp',
                                file_url='https://example.test/private.webp', mime_type='image/webp', file_size_kb=1)
        response = self.client.get(f'/api/submissions/{self.entry.pk}/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['documents'], [])
        self.assertEqual(response.data['drive_archives'], [])
        self.assertEqual(self.client.get(f'/api/submissions/{self.foreign.pk}/').status_code, 404)
        self.assertEqual(self.client.get('/api/documents/').status_code, 403)

    @patch('submissions.serializers.send_status_change_email')
    def test_saved_status_and_remarks_are_freshly_readable_by_peer(self, email):
        self.client.force_authenticate(self.staff)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(f'/api/submissions/{self.entry.pk}/status/',
                                         {'status': 'approved', 'remarks_text': 'Organization update'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.client.force_authenticate(self.peer)
        self.assertEqual(self.client.get(f'/api/submissions/{self.entry.pk}/').data['status'], 'approved')
        history = self.rows('/api/review-logs/', submission_id=str(self.entry.pk))
        self.assertEqual(history[0]['remarks_text'], 'Organization update')
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.rows('/api/review-logs/', submission_id=str(self.entry.pk)), [])
        self.assertEqual(self.client.get(f"/api/review-logs/{history[0]['log_id']}/").status_code, 404)

    def test_peer_cannot_edit_prioritize_change_status_or_delete(self):
        for suffix, method, payload in [
            ('', 'patch', {'title': 'Not allowed'}),
            ('status/', 'patch', {'status': 'approved', 'priority_escalation': True}),
            ('', 'delete', {'confirmation': 'DELETE', 'reason_type': 'incorrect'}),
        ]:
            response = getattr(self.client, method)(f'/api/submissions/{self.entry.pk}/{suffix}', payload, format='json')
            self.assertEqual(response.status_code, 403, response.data)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.title, 'Shared entry')
        self.assertEqual(self.entry.status, 'under_review')

    def test_unassigned_students_do_not_share_a_null_organization(self):
        own = Submission.objects.create(title='Unassigned own', submitted_by=self.unassigned)
        self.client.force_authenticate(self.unassigned)
        self.assertEqual([row['submission_id'] for row in self.rows('/api/submissions/')], [str(own.pk)])
        self.assertEqual(self.client.get(f'/api/submissions/{self.legacy.pk}/').status_code, 404)

    def test_audit_shares_submission_updates_but_not_peers_private_login_activity(self):
        log_login(self.owner)
        log_status_change(self.staff, 'tbl_Submissions', self.entry.pk, 'pending', 'under_review')
        log_status_change(self.staff, 'tbl_Submissions', self.foreign.pk, 'pending', 'under_review')
        rows = self.rows('/api/audit-logs/')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['table_name'], 'tbl_Submissions')

    def test_membership_change_updates_scope_and_staff_retains_all_records(self):
        self.peer.org_id = self.other_org
        self.peer.save(update_fields=['org_id'])
        rows = self.rows('/api/submissions/')
        # A transfer starts a NEW actual membership; older Organization B submissions stay hidden.
        self.assertEqual({row['submission_id'] for row in rows}, {str(self.legacy.pk)})
        self.assertEqual(self.client.get(f'/api/submissions/{self.entry.pk}/').status_code, 404)
        self.client.force_authenticate(self.staff)
        self.assertEqual(len(self.rows('/api/submissions/')), 3)

    @override_settings(NOTIFICATIONS_PUSH_ENABLED=True)
    @patch('notifications.tasks.send_push.delay')
    def test_creation_status_and_priority_alerts_remain_submitter_only(self, push):
        self.client.force_authenticate(self.staff)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post('/api/submissions/', {
                'title': 'Organization receipt', 'org_id': str(self.org.pk),
                'submitted_by': str(self.owner.pk),
            }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        entry_id = response.data['submission_id']
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(f'/api/submissions/{entry_id}/status/',
                                         {'status': 'approved', 'priority_escalation': True}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        notifications = Notification.objects.filter(submission_id=entry_id)
        self.assertEqual(notifications.count(), 3)
        self.assertEqual(set(notifications.values_list('user_id', flat=True)), {self.owner.pk})
        self.assertEqual(push.call_count, 3)
        self.assertEqual(len(mail.outbox), 3)
        self.assertTrue(all(message.to == [self.owner.email] for message in mail.outbox))
        self.client.force_authenticate(self.peer)
        self.assertEqual(self.client.get(f'/api/submissions/{entry_id}/').status_code, 200)
        self.assertEqual(self.client.get('/api/notifications/').data['results'], [])
