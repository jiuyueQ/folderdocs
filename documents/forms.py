from pathlib import Path
from django import forms
from django.conf import settings
from PIL import Image
from pypdf import PdfReader


class UploadForm(forms.Form):
    file = forms.FileField(label='选择文件')

    def clean_file(self):
        upload = self.cleaned_data['file']
        if upload.size > settings.MAX_DOCUMENT_BYTES:
            raise forms.ValidationError('单个文件不能超过 25 MB。')
        if not upload.size:
            raise forms.ValidationError('不能上传空文件。')
        suffix = Path(upload.name).suffix.lower()
        try:
            if suffix == '.pdf':
                reader = PdfReader(upload)
                if reader.is_encrypted:
                    raise forms.ValidationError('请先解密 PDF 再上传。')
                if not reader.pages or len(reader.pages) > 100:
                    raise forms.ValidationError('PDF 必须包含 1–100 页。')
            elif suffix in {'.png', '.jpg', '.jpeg', '.webp'}:
                with Image.open(upload) as image:
                    expected = {'.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG', '.webp': 'WEBP'}[suffix]
                    if image.format != expected:
                        raise forms.ValidationError('图片内容与扩展名不符，请使用正确的扩展名。')
                    if image.width * image.height > 30_000_000:
                        raise forms.ValidationError('图片不能超过 3000 万像素。')
                    image.verify()
            elif suffix == '.txt':
                upload.read().decode('utf-8-sig')
            else:
                raise forms.ValidationError('支持 PDF、PNG、JPG、WEBP 和 UTF-8 TXT。')
        except forms.ValidationError:
            raise
        except Exception as exc:
            raise forms.ValidationError('文件无法读取，或内容与文件类型不符。') from exc
        finally:
            upload.seek(0)
        return upload
