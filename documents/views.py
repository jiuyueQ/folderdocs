import hashlib
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Case, Count, F, Q, Sum, Value, When
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from .forms import UploadForm
from .models import Document, Folder


def owned(request, pk, **kwargs):
    return get_object_or_404(Document, pk=pk, owner=request.user, **kwargs)


def selected_folder(request, key):
    if not key:
        return None
    try:
        return get_object_or_404(Folder, pk=key, owner=request.user)
    except (ValidationError, ValueError):
        raise Http404('文件夹不存在。')


def register(request):
    if request.user.is_authenticated:
        return redirect('library')
    form = UserCreationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.save())
        return redirect('library')
    return render(request, 'registration/register.html', {'form': form})


@login_required
def library(request):
    all_docs = Document.objects.filter(owner=request.user)
    active = all_docs.filter(deleted_at__isnull=True)
    mode = request.GET.get('view', 'all')
    folder = selected_folder(request, request.GET.get('folder'))
    docs = all_docs.filter(deleted_at__isnull=False) if mode == 'trash' else active
    if mode == 'inbox':
        docs = docs.filter(folder__isnull=True)
    if folder:
        docs = docs.filter(folder=folder)
    query = request.GET.get('q', '').strip()[:200]
    if query:
        docs = docs.filter(Q(title__icontains=query) | Q(original_name__icontains=query) | Q(text__icontains=query))
    state = request.GET.get('state', '')
    if state in Document.Status.values:
        docs = docs.filter(status=state)
    kind = request.GET.get('kind', '')
    if kind in {'pdf', 'image', 'txt'}:
        docs = docs.filter(kind=kind)
    page = Paginator(docs.select_related('folder'), 12).get_page(request.GET.get('page'))
    for doc in page:
        position = doc.text.casefold().find(query.casefold()) if query else -1
        doc.snippet = doc.text[max(0, position - 35):max(0, position - 35) + 140].replace('\n', ' ')
    filters = request.GET.copy()
    filters.pop('page', None)
    return render(request, 'documents/library.html', {
        'page': page, 'folders': Folder.objects.filter(owner=request.user).annotate(
            document_count=Count('document', filter=Q(document__deleted_at__isnull=True))),
        'folder': folder, 'query': query, 'mode': mode, 'state': state, 'kind': kind,
        'stats': active.aggregate(total=Count('id'), ready=Count('id', filter=Q(status='ready')),
            pending=Count('id', filter=Q(status__in=['pending', 'processing'])), bytes=Sum('size')),
        'trash_count': all_docs.filter(deleted_at__isnull=False).count(),
        'inbox_count': active.filter(folder__isnull=True).count(), 'filter_query': filters.urlencode(),
    })


@login_required
@require_POST
def create_folder(request):
    name = request.POST.get('name', '').strip()
    if not name or len(name) > 80:
        messages.error(request, '文件夹名称需要 1–80 个字符。')
        return redirect('library')
    try:
        with transaction.atomic():
            folder = Folder.objects.create(owner=request.user, name=name)
    except IntegrityError:
        messages.error(request, '已存在同名文件夹。')
        return redirect('library')
    return redirect('/?folder=' + str(folder.pk))


@login_required
@require_POST
def delete_folder(request, pk):
    folder = get_object_or_404(Folder, pk=pk, owner=request.user)
    folder.delete()
    messages.success(request, '文件夹已移除，文档保留在待归档中。')
    return redirect('library')


@login_required
@require_POST
def upload(request):
    folder = selected_folder(request, request.POST.get('folder'))
    files = request.FILES.getlist('files')
    if not files or len(files) > 20:
        messages.error(request, '每次请选择 1–20 个文件。')
        return redirect('library')
    for file in files:
        form = UploadForm({}, {'file': file})
        if not form.is_valid():
            messages.error(request, f'{file.name}: {form.errors["file"][0]}')
            continue
        digest = hashlib.sha256()
        for chunk in file.chunks():
            digest.update(chunk)
        checksum = digest.hexdigest()
        file.seek(0)
        if Document.objects.filter(owner=request.user, checksum=checksum, deleted_at__isnull=True).exists():
            messages.info(request, f'{file.name} 已存在，已跳过重复上传。')
            continue
        suffix = Path(file.name).suffix.lower()
        doc = Document(owner=request.user, folder=folder, title=Path(file.name).stem[:200],
            original_name=file.name[:255], kind='pdf' if suffix == '.pdf' else 'txt' if suffix == '.txt' else 'image',
            size=file.size, checksum=checksum)
        doc.file.save(file.name, file, save=False)
        try:
            doc.save()
        except Exception:
            doc.file.delete(save=False)
            raise
        messages.success(request, f'{file.name} 已加入识别队列。')
    return redirect('/?folder=' + str(folder.pk) if folder else 'library')


@login_required
def detail(request, pk):
    doc = owned(request, pk)
    active = Document.objects.filter(owner=request.user, deleted_at__isnull=True)
    return render(request, 'documents/detail.html', {
        'doc': doc, 'folders': Folder.objects.filter(owner=request.user).annotate(
            document_count=Count('document', filter=Q(document__deleted_at__isnull=True))),
        'stats': {'total': active.count()}, 'inbox_count': active.filter(folder__isnull=True).count(),
        'trash_count': Document.objects.filter(owner=request.user, deleted_at__isnull=False).count(),
    })


@login_required
def file_view(request, pk):
    doc = owned(request, pk, deleted_at__isnull=True)
    types = {'pdf': 'application/pdf', 'image': 'image/jpeg', 'txt': 'text/plain; charset=utf-8'}
    if doc.kind == 'image':
        types['image'] = {'.png': 'image/png', '.webp': 'image/webp', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg'}[Path(doc.file.name).suffix]
    try:
        response = FileResponse(doc.file.open('rb'), content_type=types[doc.kind],
            as_attachment=request.GET.get('download') == '1', filename=doc.original_name)
    except FileNotFoundError:
        raise Http404('原始文件已离线或丢失。')
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
def thumbnail(request, pk):
    doc = owned(request, pk, deleted_at__isnull=True)
    if not doc.thumbnail:
        raise Http404
    try:
        response = FileResponse((settings.MEDIA_ROOT / doc.thumbnail).open('rb'), content_type='image/png')
    except FileNotFoundError:
        raise Http404
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
@require_POST
def retry(request, pk):
    doc = owned(request, pk, deleted_at__isnull=True)
    Document.objects.filter(pk=doc.pk, status='failed').update(status='pending', error='', lease=None)
    return redirect('detail', pk=pk)


@login_required
@require_POST
def move(request, pk):
    doc = owned(request, pk, deleted_at__isnull=True)
    folder = selected_folder(request, request.POST.get('folder'))
    title = request.POST.get('title', '').strip()
    if not title or len(title) > 200:
        messages.error(request, '文档标题需要 1–200 个字符。')
        return redirect('detail', pk=pk)
    Document.objects.filter(pk=doc.pk, deleted_at__isnull=True).update(folder=folder, title=title)
    messages.success(request, '文档信息已更新。')
    return redirect('detail', pk=pk)


@login_required
@require_POST
def delete(request, pk):
    doc = owned(request, pk)
    Document.objects.filter(pk=doc.pk).update(deleted_at=timezone.now(), lease=None)
    messages.success(request, '已移入回收站。')
    return redirect('library')


@login_required
@require_POST
def restore(request, pk):
    doc = owned(request, pk, deleted_at__isnull=False)
    Document.objects.filter(pk=doc.pk, deleted_at__isnull=False).update(
        deleted_at=None, status=Case(When(status='processing', then=Value('pending')), default=F('status')))
    messages.success(request, '文档已恢复。')
    return redirect('library')


@login_required
@require_POST
def purge(request, pk):
    doc = owned(request, pk, deleted_at__isnull=False)
    try:
        with transaction.atomic():
            if not Document.objects.filter(pk=doc.pk, deleted_at__isnull=False).update(lease=None):
                raise Http404('文档已恢复。')
            if doc.thumbnail:
                (settings.MEDIA_ROOT / doc.thumbnail).unlink(missing_ok=True)
            doc.file.storage.delete(doc.file.name)
            doc.delete()
    except PermissionError:
        messages.error(request, '文件正在预览或下载，请关闭后重试。')
        return redirect('detail', pk=pk)
    messages.success(request, '文档已永久删除。')
    return redirect('/?view=trash')


@login_required
def status(request):
    docs = Document.objects.filter(owner=request.user, deleted_at__isnull=True)
    return JsonResponse({'pending': docs.filter(status__in=['pending', 'processing']).count(),
        'revision': list(docs.values_list('id', 'status'))}, json_dumps_params={'default': str})
