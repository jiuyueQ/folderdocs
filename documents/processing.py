import io
import os
import shutil
import uuid
from datetime import timedelta
from pathlib import Path
import pymupdf as fitz
import pytesseract
from PIL import Image, ImageOps
from django.conf import settings
from django.db.models import F
from django.utils import timezone
from .models import Document


def configure_ocr():
    candidates = [settings.TESSERACT_CMD, shutil.which('tesseract'),
        str(settings.BASE_DIR / '.tools' / 'tesseract' / 'tesseract.exe'),
        str(settings.BASE_DIR / '.tools' / 'ocr' / 'Library' / 'bin' / 'tesseract.exe'),
        r'C:\Program Files\Tesseract-OCR\tesseract.exe']
    binary = next((item for item in candidates if item and Path(item).is_file()), None)
    if not binary:
        raise RuntimeError('未找到 Tesseract OCR。请运行 OCR 安装步骤，再点击重新处理。')
    pytesseract.pytesseract.tesseract_cmd = binary
    data_candidates = [settings.TESSDATA_PREFIX, Path(binary).parent / 'tessdata',
        Path(binary).parent.parent / 'share' / 'tessdata',
        Path(binary).parent.parent.parent / 'share' / 'tessdata']
    data_path = next((Path(path) for path in data_candidates if path and
        ((Path(path) / 'eng.traineddata').is_file() or (Path(path) / 'chi_sim.traineddata').is_file())), None)
    if data_path:
        os.environ['TESSDATA_PREFIX'] = str(data_path)
    languages = pytesseract.get_languages(config='')
    wanted = [lang for lang in ['chi_sim', 'eng'] if lang in languages]
    if not wanted:
        raise RuntimeError('缺少 OCR 语言包，请安装 eng 或 chi_sim。')
    return '+'.join(wanted)


def ocr(image):
    language = configure_ocr()
    return pytesseract.image_to_string(image, lang=language, config='--psm 3', timeout=60)


def extract(doc):
    with doc.file.open('rb') as stream:
        content = stream.read()
    if doc.kind == 'txt':
        return content.decode('utf-8-sig'), 1, None, ''
    if doc.kind == 'image':
        with Image.open(io.BytesIO(content)) as original:
            image = ImageOps.exif_transpose(original).convert('RGB')
            text = ocr(image)
            return text, 1, image, ''
    texts, preview, skipped = [], None, 0
    with fitz.open(stream=content, filetype='pdf') as pdf:
        for index, page in enumerate(pdf):
            text = page.get_text().strip()
            if preview is None or (not text and index < settings.OCR_MAX_PAGES):
                if page.rect.width <= 0 or page.rect.height <= 0:
                    raise RuntimeError('PDF 页面尺寸无效。')
                scale = min(2, 2400 / max(page.rect.width, page.rect.height))
                bitmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                image = Image.frombytes('RGB', [bitmap.width, bitmap.height], bitmap.samples)
                if preview is None:
                    preview = image.copy()
                if not text and index < settings.OCR_MAX_PAGES:
                    text = ocr(image)
            elif not text:
                skipped += 1
            texts.append(text)
        note = f'有 {skipped} 页扫描件未识别：第一版仅对前 {settings.OCR_MAX_PAGES} 页进行 OCR。' if skipped else ''
        return '\n\n'.join(texts), len(pdf), preview, note


def process_next():
    stale = timezone.now() - timedelta(hours=2)
    Document.objects.filter(status='processing', deleted_at__isnull=True, started_at__lt=stale).update(
        status='pending', lease=None, note='上次任务中断，已重新加入队列。')
    candidate = Document.objects.filter(status='pending', deleted_at__isnull=True).order_by('created_at').first()
    if candidate is None:
        return False
    lease = uuid.uuid4()
    changed = Document.objects.filter(pk=candidate.pk, status='pending', deleted_at__isnull=True).update(
        status='processing', lease=lease, started_at=timezone.now(), attempts=F('attempts') + 1)
    if not changed:
        return True
    destination = None
    try:
        text, pages, preview, note = extract(candidate)
        thumbnail = ''
        if preview:
            preview.thumbnail((620, 760))
            thumbnail = f'previews/{candidate.owner_id}/{candidate.id}-{lease}.png'
            destination = settings.MEDIA_ROOT / thumbnail
            destination.parent.mkdir(parents=True, exist_ok=True)
            preview.save(destination, format='PNG')
        updated = Document.objects.filter(pk=candidate.pk, lease=lease, deleted_at__isnull=True).update(
            status='ready', text=text[:2_000_000], page_count=pages, thumbnail=thumbnail,
            note=note or ('没有识别到文字，可下载原文件查看。' if not text.strip() else ''),
            error='', lease=None, processed_at=timezone.now())
        if not updated and destination:
            destination.unlink(missing_ok=True)
    except Exception as exc:
        if destination:
            destination.unlink(missing_ok=True)
        error = str(exc) if isinstance(exc, RuntimeError) else '文档处理失败。请检查原文件是否可读，或查看后台日志。'
        Document.objects.filter(pk=candidate.pk, lease=lease, deleted_at__isnull=True).update(
            status='failed', error=error[:1000], lease=None, processed_at=timezone.now())
        import logging
        logging.getLogger(__name__).exception('Document processing failed: %s', candidate.pk)
    return True
