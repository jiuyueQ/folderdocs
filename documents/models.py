import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Folder(models.Model):
    MAX_DEPTH = 8
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    parent = models.ForeignKey('self', on_delete=models.RESTRICT, null=True, blank=True, related_name='children')
    name = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['owner', 'name'], condition=models.Q(parent__isnull=True), name='unique_root_folder'),
            models.UniqueConstraint(fields=['owner', 'parent', 'name'], name='unique_sibling_folder'),
            models.CheckConstraint(condition=~models.Q(parent=models.F('id')), name='folder_not_own_parent'),
        ]

    def clean(self):
        super().clean()
        self.name = self.name.strip()
        if not self.name or len(self.name) > 80:
            raise ValidationError('文件夹名称需要 1–80 个字符。')
        graph = dict(Folder.objects.filter(owner_id=self.owner_id).values_list('pk', 'parent_id'))
        if self.parent_id and self.parent_id not in graph:
            raise ValidationError('上级文件夹不存在或不属于当前用户。')
        graph[self.pk] = self.parent_id
        for node in graph:
            seen = set()
            current = node
            while current is not None:
                if current in seen:
                    raise ValidationError('不能将文件夹移动到自身或其子文件夹中。')
                seen.add(current)
                if len(seen) > self.MAX_DEPTH:
                    raise ValidationError(f'文件夹最多支持 {self.MAX_DEPTH} 层，请选择更靠近根目录的位置。')
                if current not in graph:
                    raise ValidationError('文件夹层级无效。')
                current = graph[current]
        if Folder.objects.filter(owner_id=self.owner_id, parent_id=self.parent_id, name=self.name).exclude(pk=self.pk).exists():
            raise ValidationError('同一位置已存在同名文件夹。')


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
