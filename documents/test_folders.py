"""Hierarchy permissions, data preservation and upgrade regression checks."""
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import RestrictedError
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from .folders import folder_tree
from .models import Document, Folder
from .processing import process_next


class FolderHierarchyTests(TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        media = override_settings(MEDIA_ROOT=Path(temp.name))
        media.enable()
        self.addCleanup(temp.cleanup)
        self.addCleanup(media.disable)
        self.alice = get_user_model().objects.create_user('alice')
        self.bob = get_user_model().objects.create_user('bob')
        self.client.force_login(self.alice)
        self.home = Folder.objects.create(owner=self.alice, name='家庭')
        self.bills = Folder.objects.create(owner=self.alice, name='账单', parent=self.home)
        self.year = Folder.objects.create(owner=self.alice, name='2026', parent=self.bills)
        self.work = Folder.objects.create(owner=self.alice, name='工作')
        self.foreign = Folder.objects.create(owner=self.bob, name='BOB-PRIVATE')

    def edit(self, folder, parent=None, name=None, **kwargs):
        return self.client.post(f'/folders/{folder.pk}/edit/', {
            'name': folder.name if name is None else name,
            'parent': str(parent.pk) if parent else '',
        }, **kwargs)

    def upload(self, folder, token):
        self.client.post('/upload/', {'folder': str(folder.pk),
            'files': SimpleUploadedFile(token + '.txt', ('Search token ' + token).encode())})
        doc = Document.objects.get(owner=self.alice, title=token)
        self.assertTrue(process_next())
        doc.refresh_from_db()
        return doc

    def test_duplicate_names_only_rejected_in_same_parent(self):
        self.client.post('/folders/create/', {'name': '  账单  ', 'parent': str(self.work.pk)})
        self.assertTrue(Folder.objects.filter(parent=self.work, name='账单').exists())
        before = Folder.objects.count()
        for name, parent in [('家庭', ''), ('账单', str(self.home.pk)), (' ', ''), ('a' * 81, '')]:
            self.client.post('/folders/create/', {'name': name, 'parent': parent})
        self.assertEqual(Folder.objects.count(), before)
        self.edit(self.work, name='家庭')
        self.work.refresh_from_db()
        self.assertEqual(self.work.name, '工作')
        other = Folder.objects.get(parent=self.work, name='账单')
        self.edit(other, parent=self.home)
        other.refresh_from_db()
        self.assertEqual(other.parent_id, self.work.pk)

    def test_hierarchy_routes_reject_foreign_and_malformed_ids(self):
        for parent in [str(self.foreign.pk), 'bad-id']:
            self.assertEqual(self.client.post('/folders/create/', {'name': 'new', 'parent': parent}).status_code, 404)
            self.assertEqual(self.client.post(f'/folders/{self.bills.pk}/edit/', {'name': 'new', 'parent': parent}).status_code, 404)
        for suffix in ['edit', 'delete']:
            self.assertEqual(self.client.post(f'/folders/{self.foreign.pk}/{suffix}/', {'name': 'new'}).status_code, 404)
        self.bills.refresh_from_db()
        self.assertEqual(self.bills.parent_id, self.home.pk)
        page = self.client.get('/')
        self.assertNotContains(page, 'BOB-PRIVATE')
        self.assertEqual(self.client.get('/', {'folder': str(self.foreign.pk), 'recursive': '1'}).status_code, 404)

    def test_cycle_and_descendant_moves_rejected_without_partial_rename(self):
        for target in [self.home, self.bills, self.year]:
            response = self.edit(self.home, parent=target, name='should-not-save', follow=True)
            self.assertContains(response, '不能将文件夹移动到自身或其子文件夹中')
            self.home.refresh_from_db()
            self.assertIsNone(self.home.parent_id)
            self.assertEqual(self.home.name, '家庭')
        page = self.client.get('/', {'folder': str(self.home.pk)})
        self.assertEqual([item.pk for item in page.context['move_targets']], [self.work.pk])

    def test_depth_limit_includes_entire_moving_subtree(self):
        parent = self.work
        for depth in range(2, 9):
            self.client.post('/folders/create/', {'name': f'level-{depth}', 'parent': str(parent.pk)})
            parent = Folder.objects.get(name=f'level-{depth}', owner=self.alice)
        before = Folder.objects.count()
        response = self.client.post('/folders/create/', {'name': 'level-9', 'parent': str(parent.pk)}, follow=True)
        self.assertContains(response, '最多支持 8 层')
        self.assertEqual(Folder.objects.count(), before)
        # The moved root itself fits at level 7, but its grandchild would be level 9.
        sixth = Folder.objects.get(name='level-6')
        response = self.edit(self.home, parent=sixth, follow=True)
        self.assertContains(response, '最多支持 8 层')
        self.home.refresh_from_db()
        self.assertIsNone(self.home.parent_id)
        fifth = Folder.objects.get(name='level-5')
        self.edit(self.home, parent=fifth)
        self.home.refresh_from_db()
        self.assertEqual(self.home.parent_id, fifth.pk)
        self.assertEqual(next(item.depth for item in folder_tree(self.alice) if item.pk == self.year.pk), 7)

    def test_rename_move_subtree_preserves_originals_search_and_folder_ids(self):
        doc = self.upload(self.year, 'FOLDER-MOVE-42')
        original_path = doc.file.name
        original = Path(doc.file.path).read_bytes()
        self.edit(self.bills, parent=self.work, name='发票')
        doc.refresh_from_db()
        self.year.refresh_from_db()
        self.assertEqual(doc.folder_id, self.year.pk)
        self.assertEqual(self.year.parent_id, self.bills.pk)
        self.assertEqual(doc.file.name, original_path)
        self.assertEqual(Path(doc.file.path).read_bytes(), original)
        page = self.client.get('/', {'folder': str(self.work.pk), 'recursive': '1', 'q': 'FOLDER-MOVE-42'})
        self.assertEqual(page.context['page'].paginator.count, 1)
        self.assertContains(page, '工作 / 发票 / 2026')
        page = self.client.get('/', {'folder': str(self.year.pk)})
        self.assertEqual([item.name for item in page.context['breadcrumbs']], ['工作', '发票', '2026'])
        self.edit(self.bills, name='发票')
        self.assertEqual(next(item.path for item in folder_tree(self.alice) if item.pk == self.year.pk), '发票 / 2026')

    def test_recursive_filters_pagination_and_tree_counts(self):
        direct = self.upload(self.home, 'DIRECT')
        trashed = self.upload(self.year, 'TRASHED')
        self.client.post(f'/documents/{trashed.pk}/delete/')
        for index in range(13):
            Document.objects.create(owner=self.alice, folder=self.year, title=f'SEARCH-{index}',
                original_name=f'{index}.txt', file=f'originals/test-{index}.txt', kind='txt',
                size=1, checksum=str(index), status='ready', text='MATCH-TOKEN')
        Document.objects.create(owner=self.bob, folder=self.foreign, title='MATCH-TOKEN',
            original_name='private.txt', kind='txt', size=1, checksum='private', status='ready')
        page = self.client.get('/', {'folder': str(self.home.pk)})
        self.assertEqual([doc.pk for doc in page.context['page']], [direct.pk])
        params = {'folder': str(self.home.pk), 'recursive': '1', 'q': 'MATCH-TOKEN', 'kind': 'txt', 'state': 'ready', 'page': '2'}
        page = self.client.get('/', params)
        self.assertEqual(page.context['page'].paginator.count, 13)
        self.assertEqual(len(page.context['page']), 1)
        self.assertContains(page, 'name="recursive" value="1"')
        self.assertIn('recursive=1', page.context['filter_query'])
        self.assertNotIn('page=', page.context['filter_query'])
        tree = {item.pk: item for item in page.context['folders']}
        self.assertEqual(tree[self.home.pk].document_count, 1)
        self.assertEqual(tree[self.year.pk].document_count, 13)
        self.assertEqual(tree[self.home.pk].child_count, 1)
        self.assertNotIn(self.foreign.pk, tree)
        trash = self.client.get('/', {'folder': str(self.home.pk), 'recursive': '1', 'view': 'trash'})
        self.assertEqual([doc.pk for doc in trash.context['page']], [trashed.pk])

    def test_leaf_removal_reparents_active_and_trashed_documents(self):
        active = self.upload(self.year, 'KEEP-ACTIVE')
        trashed = self.upload(self.year, 'KEEP-TRASH')
        self.client.post(f'/documents/{trashed.pk}/delete/')
        originals = {doc.pk: (doc.file.name, Path(doc.file.path).read_bytes()) for doc in [active, trashed]}
        response = self.client.post(f'/folders/{self.year.pk}/delete/')
        self.assertRedirects(response, '/?folder=' + str(self.bills.pk))
        for doc in [active, trashed]:
            doc.refresh_from_db()
            self.assertEqual(doc.folder_id, self.bills.pk)
            self.assertEqual(doc.file.name, originals[doc.pk][0])
            self.assertEqual(Path(doc.file.path).read_bytes(), originals[doc.pk][1])
        self.assertIsNotNone(trashed.deleted_at)
        self.client.post(f'/documents/{trashed.pk}/restore/')
        trashed.refresh_from_db()
        self.assertIsNone(trashed.deleted_at)
        self.assertEqual(trashed.folder_id, self.bills.pk)

    def test_parent_removal_blocked_and_database_restricts_direct_delete(self):
        doc = self.upload(self.bills, 'KEEP-PARENT')
        page = self.client.post(f'/folders/{self.bills.pk}/delete/', follow=True)
        self.assertContains(page, '请先移动或移除子文件夹')
        self.assertTrue(Folder.objects.filter(pk=self.bills.pk).exists())
        doc.refresh_from_db()
        self.assertEqual(doc.folder_id, self.bills.pk)
        with self.assertRaises(RestrictedError):
            self.home.delete()
        # An owner's full cascade may remove the whole hierarchy together.
        owner_id = self.alice.pk
        self.alice.delete()
        self.assertFalse(Folder.objects.filter(owner_id=owner_id).exists())
        self.assertTrue(Folder.objects.filter(pk=self.foreign.pk).exists())

    def test_post_csrf_and_escaping(self):
        for url in ['/folders/create/', f'/folders/{self.home.pk}/edit/', f'/folders/{self.home.pk}/delete/']:
            self.assertEqual(self.client.get(url).status_code, 405)
            strict = Client(enforce_csrf_checks=True)
            strict.force_login(self.alice)
            self.assertEqual(strict.post(url, {'name': 'new'}).status_code, 403)
        self.client.post('/folders/create/', {'name': '<script>alert(1)</script>', 'parent': str(self.work.pk)})
        page = self.client.get('/', {'folder': str(self.work.pk)})
        self.assertContains(page, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(page, '<script>alert(1)</script>')
        self.client.logout()
        self.assertEqual(self.edit(self.home).status_code, 302)

    def test_database_constraints_for_roots_siblings_and_self_parent(self):
        for values in [{'name': '家庭'}, {'name': '账单', 'parent': self.home},
                       {'name': 'self', 'id': self.work.pk, 'parent': self.work}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                if 'id' in values:
                    Folder.objects.filter(pk=self.work.pk).update(parent=self.work)
                else:
                    Folder.objects.create(owner=self.alice, **values)


class FolderUpgradeTests(TransactionTestCase):
    def test_upgrade_keeps_existing_roots_and_document_metadata(self):
        old_target = [('documents', '0001_initial')]
        latest = [('documents', '0002_remove_folder_unique_owner_folder_folder_parent_and_more')]
        executor = MigrationExecutor(connection)
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        executor.migrate(old_target)
        old = executor.loader.project_state(old_target).apps
        owner = old.get_model('auth', 'User').objects.create(username='legacy-user')
        folder = old.get_model('documents', 'Folder').objects.create(owner=owner, name='旧文件夹')
        doc = old.get_model('documents', 'Document').objects.create(owner=owner, folder=folder,
            title='旧文档', original_name='original.txt', file='originals/legacy.txt', size=42,
            checksum='legacy-checksum', kind='txt', status='ready', text='legacy text', deleted_at=timezone.now())
        MigrationExecutor(connection).migrate(latest)
        upgraded = Folder.objects.get(pk=folder.pk)
        retained = Document.objects.get(pk=doc.pk)
        self.assertIsNone(upgraded.parent_id)
        self.assertEqual(upgraded.name, '旧文件夹')
        self.assertEqual(retained.folder_id, folder.pk)
        self.assertEqual(retained.file.name, 'originals/legacy.txt')
        self.assertEqual(retained.checksum, 'legacy-checksum')
        self.assertEqual(retained.text, 'legacy text')
        self.assertIsNotNone(retained.deleted_at)
        Folder.objects.create(owner_id=owner.pk, name='旧文件夹', parent=upgraded)
