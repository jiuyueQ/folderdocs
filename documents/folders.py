"""Owner-scoped folder tree and serialized hierarchy mutations."""
from django.contrib.auth import get_user_model
from django.db.models import Count, F, Q
from .models import Folder


def lock_hierarchy(owner):
    # First write in an atomic transaction: serializes SQLite mutations, and
    # acquires the owner's row lock on databases with row-level locking.
    get_user_model().objects.filter(pk=owner.pk).update(last_login=F('last_login'))


def folder_tree(owner):
    rows = list(Folder.objects.filter(owner=owner).annotate(
        document_count=Count('document', filter=Q(document__deleted_at__isnull=True))))
    by_parent = {}
    for item in rows:
        by_parent.setdefault(item.parent_id, []).append(item)
    result = []

    def visit(parent, ancestors):
        for item in by_parent.get(parent, []):
            item.depth = len(ancestors)
            item.child_count = len(by_parent.get(item.pk, []))
            item.ancestors = ancestors
            item.path = ' / '.join([node.name for node in ancestors] + [item.name])
            item.descendant_ids = {item.pk}
            result.append(item)
            visit(item.pk, ancestors + [item])
            for child in by_parent.get(item.pk, []):
                item.descendant_ids.update(child.descendant_ids)

    visit(None, [])
    return result
