import io
import secrets
import hashlib
import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFont
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from documents.models import Document, Folder


class Command(BaseCommand):
    help = 'Create synthetic demonstration documents; never modifies an existing account.'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='demo')

    def handle(self, *args, **options):
        username = options['username']
        if get_user_model().objects.filter(username=username).exists():
            raise CommandError('Account already exists. Choose a new demo username.')
        password = secrets.token_urlsafe(15)
        user = get_user_model().objects.create_user(username=username, password=password)
        folders = {name: Folder.objects.create(owner=user, name=name) for name in ['家庭账单', '合同与凭证', '学习资料', '旅行记录']}
        items = [('家用电器购买凭证', '家庭账单', 'PURCHASE RECEIPT', 'Receipt No. FD-2026-014 | Amount CNY 1,280 | Warranty 24 months'),
            ('房屋租赁合同', '合同与凭证', 'RENTAL AGREEMENT', 'Agreement No. FD-2026-008 | Lease 12 months | Deposit CNY 3,000'),
            ('周末旅行计划', '旅行记录', 'WEEKEND JOURNEY', 'Day 1 - Botanical garden | Day 2 - Lakeside walk | Budget CNY 600'),
            ('Python 学习笔记', '学习资料', 'PYTHON FIELD NOTES', 'Topics: pathlib, context managers, database transactions and background jobs'),
            ('设备保修说明', '合同与凭证', 'WARRANTY RECORD', 'Warranty expires 2027-10-14 | Support code WARRANTY-2027')]
        for title, folder_name, heading, body in items:
            with fitz.open() as pdf:
                page = pdf.new_page(width=480, height=630)
                page.draw_rect(fitz.Rect(0, 0, 480, 10), color=None, fill=(.18, .38, .29))
                page.insert_text((40, 65), 'FOLDERDOCS / DEMO ARCHIVE', fontsize=10, color=(.46, .55, .42))
                page.insert_text((40, 115), heading, fontsize=21, color=(.18, .3, .23))
                page.insert_text((40, 150), title, fontname='china-s', fontsize=15, color=(.35, .46, .31))
                page.draw_line((40, 174), (440, 174), color=(.83, .88, .8))
                for index, line in enumerate(body.split(' | ')):
                    page.insert_text((40, 225 + index * 38), line, fontsize=11, color=(.4, .46, .35))
                for index in range(5):
                    page.draw_line((40, 410 + index * 22), (390 - (index % 3) * 40, 410 + index * 22), color=(.89, .91, .85))
                page.insert_text((40, 585), 'Synthetic example - no real personal information', fontsize=9, color=(.61, .66, .56))
                content = pdf.tobytes()
            self.save(user, folders[folder_name], title + '.pdf', content, 'pdf')
        image = Image.new('RGB', (1200, 850), 'white')
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype('arial.ttf', 44)
        except OSError:
            font = ImageFont.load_default(size=44)
        for index, text in enumerate(['FOLDERDOCS SCANNED RECEIPT', 'Order ID: OCR-2026-1280', 'Amount: 1280 CNY', 'This is a synthetic OCR test.']):
            draw.text((65, 100 + index * 140), text, fill='black', font=font)
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        self.save(user, folders['家庭账单'], '扫描账单演示.png', stream.getvalue(), 'image')
        self.stdout.write('Created 6 synthetic documents. Run manage.py worker --drain to process them.')
        self.stdout.write(f'Demo username: {username}\nDemo password: {password}')

    def save(self, user, folder, name, data, kind):
        doc = Document(owner=user, folder=folder, title=name.rsplit('.', 1)[0], original_name=name,
            kind=kind, size=len(data), checksum=hashlib.sha256(data).hexdigest())
        doc.file.save(name, ContentFile(data), save=True)
