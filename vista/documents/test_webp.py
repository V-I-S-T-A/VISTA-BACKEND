from io import BytesIO
from unittest import TestCase
from unittest.mock import patch
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from .webp import attachment_webp


class AttachmentRenderingTests(TestCase):
    def test_image_is_webp_and_keeps_content(self):
        source = BytesIO()
        Image.new('RGB', (160, 200), 'blue').save(source, 'PNG')
        data, name, size = attachment_webp(SimpleUploadedFile('scan.png', source.getvalue()))
        result = Image.open(BytesIO(data))
        self.assertEqual(result.format, 'WEBP')
        self.assertEqual(name, 'scan.webp')
        self.assertEqual(size, (160, 200))
        self.assertGreater(result.getpixel((40, 40))[2], 240)

    def test_pdf_keeps_every_page_in_one_image(self):
        with patch('documents.webp.pdfinfo_from_bytes', return_value={'Pages': 2}), patch('documents.webp.convert_from_bytes', return_value=[Image.new('RGB', (100, 120), 'red'), Image.new('RGB', (100, 120), 'blue')]):
            data, _, size = attachment_webp(SimpleUploadedFile('two.pdf', b'%PDF-test'))
        result = Image.open(BytesIO(data))
        self.assertEqual(size, (100, 240))
        self.assertGreater(result.getpixel((50, 60))[0], 240)
        self.assertGreater(result.getpixel((50, 180))[2], 240)

    def test_long_pdf_is_rejected_not_silently_truncated(self):
        with patch('documents.webp.pdfinfo_from_bytes', return_value={'Pages': 9}):
            with self.assertRaises(ValueError):
                attachment_webp(SimpleUploadedFile('long.pdf', b'%PDF-test'))
