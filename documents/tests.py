import hashlib
import io
import os
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from unittest import skipUnless
import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFont
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from .models import Document, Folder
from .processing import process_next


class DocumentFlowTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=Path(self.temp.name))
        self.override.enable()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.override.disable)
        self.alice = get_user_model().objects.create_user('alice', password='PasswordExample123!')
        self.bob = get_user_model().objects.create_user('bob', password='PasswordExample123!')
        self.client.force_login(self.alice)

    def upload(self, name='notes.txt', content=b'Warranty reference FOLDER-2026', folder=None):
        response = self.client.post('/upload/', {'files': SimpleUploadedFile(name, content), 'folder': str(folder.pk) if folder else ''})
        self.assertEqual(response.status_code, 302)
        return Document.objects.filter(owner=self.alice).first()

    def read_original(self, doc):
        with doc.file.open('rb') as stream:
            return stream.read()

    def assert_stream_status(self, path, status):
        response = self.client.get(path)
        self.assertEqual(response.status_code, status)
        response.close()

    def test_text_upload_process_search_original_unchanged(self):
        content = '家用设备保修日期：2027年，订单编号：ARCHIVE-42'.encode()
        doc = self.upload(content=content)
        self.assertEqual(doc.status, 'pending')
        self.assertTrue(process_next())
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'ready')
        self.assertIn('保修', doc.text)
        self.assertEqual(self.read_original(doc), content)
        self.assertEqual(doc.checksum, hashlib.sha256(content).hexdigest())
        page = self.client.get('/', {'q': 'ARCHIVE-42'})
        self.assertContains(page, doc.title)
        self.assertContains(page, 'ARCHIVE-42')
        self.assertEqual(page.context['page'].paginator.count, 1)

    def test_native_pdf_text_and_thumbnail(self):
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((72, 72), 'Service agreement CODE-912')
        original = pdf.tobytes()
        pdf.close()
        doc = self.upload('agreement.pdf', original)
        process_next()
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'ready')
        self.assertIn('CODE-912', doc.text)
        self.assertEqual(doc.page_count, 1)
        self.assertTrue((settings.MEDIA_ROOT / doc.thumbnail).is_file())
        self.assertEqual(self.read_original(doc), original)
        self.assert_stream_status(f'/documents/{doc.pk}/thumbnail/', 200)

    def test_every_document_route_is_private(self):
        doc = self.upload()
        process_next()
        self.client.force_login(self.bob)
        for suffix in ['', 'file/', 'thumbnail/']:
            self.assertEqual(self.client.get(f'/documents/{doc.pk}/{suffix}').status_code, 404)
        for suffix in ['retry', 'move', 'delete', 'restore', 'purge']:
            self.assertEqual(self.client.post(f'/documents/{doc.pk}/{suffix}/', {'title': 'new'}).status_code, 404)
        self.assertEqual(self.client.get('/', {'q': 'FOLDER-2026'}).context['page'].paginator.count, 0)
        self.assertEqual(self.client.get('/status/').json()['revision'], [])

    def test_private_folder_and_malformed_folder_id(self):
        foreign = Folder.objects.create(owner=self.bob, name='Private')
        for method, url, params in [('get', '/', {'folder': str(foreign.pk)}),
                ('post', '/upload/', {'folder': str(foreign.pk), 'files': SimpleUploadedFile('n.txt', b'private')}),
                ('get', '/', {'folder': 'bad-id'})]:
            self.assertEqual(getattr(self.client, method)(url, params).status_code, 404)
        doc = self.upload()
        response = self.client.post(f'/documents/{doc.pk}/move/', {'folder': str(foreign.pk), 'title': 'new'})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.post(f'/folders/{foreign.pk}/delete/').status_code, 404)

    def test_trash_restore_and_purge(self):
        doc = self.upload()
        process_next()
        original = Path(doc.file.path)
        self.client.post(f'/documents/{doc.pk}/delete/')
        self.assertTrue(original.exists())
        self.assertEqual(self.client.get(f'/documents/{doc.pk}/file/').status_code, 404)
        self.assertEqual(self.client.get('/').context['page'].paginator.count, 0)
        self.assertEqual(self.client.get('/?view=trash').context['page'].paginator.count, 1)
        self.client.post(f'/documents/{doc.pk}/restore/')
        self.assert_stream_status(f'/documents/{doc.pk}/file/', 200)
        self.assertEqual(self.client.post(f'/documents/{doc.pk}/purge/').status_code, 404)
        self.client.post(f'/documents/{doc.pk}/delete/')
        self.client.post(f'/documents/{doc.pk}/purge/')
        self.assertFalse(original.exists())
        self.assertFalse(Document.objects.filter(pk=doc.pk).exists())

    def test_reject_invalid_uploads_and_duplicates(self):
        for name, data in [('evil.html', b'<script>bad</script>'), ('fake.pdf', b'not a pdf'),
                ('fake.jpg', b'not an image'), ('empty.txt', b''), ('bad.txt', b'\xff\xfe')]:
            self.upload(name, data)
            self.assertEqual(Document.objects.count(), 0)
        self.upload()
        self.upload()
        self.assertEqual(Document.objects.count(), 1)
        with override_settings(MAX_DOCUMENT_BYTES=3):
            self.upload('large.txt', b'123456')
        self.assertEqual(Document.objects.count(), 1)

    def test_scan_ocr_failure_retry_and_preserved_original(self):
        image = Image.new('RGB', (100, 60), 'white')
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        data = stream.getvalue()
        doc = self.upload('scan.png', data)
        with patch('documents.processing.ocr', side_effect=RuntimeError('OCR not installed')):
            process_next()
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'failed')
        self.assertIn('OCR', doc.error)
        self.client.post(f'/documents/{doc.pk}/retry/')
        with patch('documents.processing.ocr', return_value='Recognition example OCR-37'):
            process_next()
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'ready')
        self.assertEqual(doc.attempts, 2)
        self.assertEqual(self.read_original(doc), data)
        self.assertEqual(self.client.get('/', {'q': 'OCR-37'}).context['page'].paginator.count, 1)

    def test_stale_task_recovery_and_delete_during_processing(self):
        doc = self.upload()
        Document.objects.filter(pk=doc.pk).update(status='processing', lease=uuid.uuid4(), started_at=timezone.now() - timedelta(hours=3))
        process_next()
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'ready')
        other = self.upload('other.txt', b'other content')
        def interrupted_extract(candidate):
            Document.objects.filter(pk=candidate.pk).update(deleted_at=timezone.now(), lease=None)
            return 'discarded', 1, Image.new('RGB', (20, 20)), ''
        with patch('documents.processing.extract', side_effect=interrupted_extract):
            process_next()
        other.refresh_from_db()
        self.assertFalse(other.text)
        self.assertEqual(list((settings.MEDIA_ROOT / 'previews').rglob('*.png')), [])

    def test_folder_removal_retains_document_and_duplicate_name(self):
        self.client.post('/folders/create/', {'name': 'Home'})
        self.client.post('/folders/create/', {'name': 'Home'})
        self.assertEqual(Folder.objects.count(), 1)
        folder = Folder.objects.get()
        doc = self.upload(folder=folder)
        self.client.post(f'/folders/{folder.pk}/delete/')
        doc.refresh_from_db()
        self.assertIsNone(doc.folder_id)
        self.assertTrue(Path(doc.file.path).is_file())

    def test_mutations_require_post_and_csrf(self):
        doc = self.upload()
        self.assertEqual(self.client.get(f'/documents/{doc.pk}/delete/').status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.alice)
        self.assertEqual(strict.post(f'/documents/{doc.pk}/delete/').status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(f'/documents/{doc.pk}/file/').status_code, 302)

    def test_registration_login_and_pagination(self):
        self.client.logout()
        self.assertEqual(self.client.get('/login/').status_code, 200)
        self.assertEqual(self.client.get('/register/').status_code, 200)
        response = self.client.post('/register/', {'username': 'charlie', 'password1': 'StrongNewPassword918!', 'password2': 'StrongNewPassword918!'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(get_user_model().objects.filter(username='charlie').exists())
        self.client.force_login(self.alice)
        for index in range(13):
            self.upload(f'note{index}.txt', f'content-{index}'.encode())
        page = self.client.get('/?page=2').context['page']
        self.assertEqual(len(page), 1)
        self.assertEqual(page.paginator.count, 13)

    @skipUnless(os.environ.get('FOLDERDOCS_TEST_OCR') == '1', 'Set FOLDERDOCS_TEST_OCR=1 for native Tesseract integration.')
    def test_real_ocr_image_and_scanned_pdf(self):
        image = Image.new('RGB', (1600, 700), 'white')
        try:
            font = ImageFont.truetype('arial.ttf', 56)
        except OSError:
            font = ImageFont.truetype('DejaVuSans.ttf', 56)
        ImageDraw.Draw(image).text((80, 180), 'ARCHIVE OCR-2026\nAmount 1280 CNY', fill='black', font=font, spacing=40)
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        png = stream.getvalue()
        with fitz.open() as pdf:
            page = pdf.new_page(width=800, height=350)
            page.insert_image(page.rect, stream=png)
            pdf_content = pdf.tobytes()
        for name, content in [('real-scan.png', png), ('real-scan.pdf', pdf_content)]:
            doc = self.upload(name, content)
            process_next()
            doc.refresh_from_db()
            self.assertEqual(doc.status, 'ready', doc.error)
            self.assertIn('1280', doc.text)
            self.assertIn('ARCHIVE', doc.text.upper())
            self.assertEqual(self.read_original(doc), content)
