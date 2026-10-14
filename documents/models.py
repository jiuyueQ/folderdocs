import uuid
from django.conf import settings
from django.db import models


class Folder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['owner', 'name'], name='unique_owner_folder')]


def original_path(instance, filename):
    from pathlib import Path
    return f'originals/{instance.owner_id}/{instance.id}{Path(filename).suffix.lower()}'


class Document(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '等待处理'
        PROCESSING = 'processing', '正在识别'
        READY = 'ready', '可搜索'
        FAILED = 'failed', '处理失败'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    folder = models.ForeignKey(Folder, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=200)
    original_name = models.CharField(max_length=255)
    file = models.FileField(upload_to=original_path)
    kind = models.CharField(max_length=10)
    size = models.PositiveBigIntegerField()
    checksum = models.CharField(max_length=64)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    text = models.TextField(blank=True)
    error = models.TextField(blank=True)
    note = models.CharField(max_length=300, blank=True)
    page_count = models.PositiveIntegerField(default=0)
    thumbnail = models.CharField(max_length=300, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    lease = models.UUIDField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['owner', 'deleted_at', 'created_at']),
                   models.Index(fields=['status', 'deleted_at', 'created_at'])]
