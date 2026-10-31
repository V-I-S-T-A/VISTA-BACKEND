from django.test import TestCase
from submissions.models import Submission
from .serializers import DocumentCreateSerializer
from submissions.views import SubmissionViewSet, SubmissionDeleteConflict


class AttachmentIdentityTests(TestCase):
    def setUp(self):
        self.submission = Submission.objects.create(title='Identity test', description='')
        self.payload = {'submission_id': str(self.submission.pk), 'file_name': 'scan.webp',
                        'file_url': 'https://res.cloudinary.com/example/image/upload/v1/scan.webp',
                        'mime_type': 'image/webp', 'file_size_kb': 10}

    def test_creation_preserves_provider_identity(self):
        serializer = DocumentCreateSerializer(data={**self.payload, 'cloudinary_public_id': 'scan', 'cloudinary_resource_type': 'image'})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        document = serializer.save()
        document.refresh_from_db()
        self.assertEqual(document.cloudinary_public_id, 'scan')
        self.assertEqual(document.cloudinary_resource_type, 'image')

    def test_partial_identity_is_rejected(self):
        for fields in ({'cloudinary_public_id': 'scan'}, {'cloudinary_resource_type': 'image'},
                       {'cloudinary_public_id': 'scan', 'cloudinary_resource_type': 'auto'}):
            serializer = DocumentCreateSerializer(data={**self.payload, **fields})
            self.assertFalse(serializer.is_valid())

    def test_legacy_clients_remain_compatible_but_deletion_still_requires_identity(self):
        serializer = DocumentCreateSerializer(data=self.payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        document = serializer.save()
        with self.assertRaises(SubmissionDeleteConflict):
            SubmissionViewSet._preflight_submission_assets(self.submission, [document])
