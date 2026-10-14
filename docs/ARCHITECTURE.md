# Architecture and acceptance criteria

## Data flow

Browser -> Django authenticated views -> original file + SQLite document row (pending)

Worker -> conditional pending/processing transition + lease -> text extraction / OCR -> preview -> conditional ready/failed transition

Browser -> owner-scoped query -> metadata + search snippet -> authenticated file stream

The document UUID forms the storage filename. The original filename remains metadata and is used for downloading. Every read, mutation, and folder assignment is checked against the authenticated owner. Files and thumbnails are never served as public static media.

Originals are immutable for OCR. Text and thumbnails are derived data. Trash stops new file downloads and invalidates the processing lease, while keeping the original recoverable. A worker completing after a trash/delete operation cannot update the document or retain its generated preview. Permanent deletion is allowed only from trash; on Windows, an open file may require the user to close the preview/download and retry.

## Windows decisions

SQLite + one Python worker keep the installation usable without Redis, Linux, or Celery. Web requests enqueue work and return immediately. Tesseract is an optional native dependency, automatically detected in a project-local Conda prefix. Waitress runs the WSGI server and WhiteNoise serves collected static assets.

The data directory, local secret, user uploads, native OCR environment, and demo credentials are excluded from Git. Startup binds only 127.0.0.1. Registration is open for local users in this milestone.

## Folder hierarchy

Folders have an optional parent within the same owner's hierarchy, with a maximum of eight levels (roots count as level one). Names are trimmed and unique among siblings; root names are separately constrained because their parent is NULL. A database check rejects self-parenting. Application validation rejects foreign parents, cycles and moves that would exceed the depth limit anywhere in the moved subtree.

Create, rename/move and delete requests begin an atomic transaction with a no-op write to the owner's user row before reading the hierarchy. This serializes SQLite hierarchy mutations and takes a row lock on databases with row-level locking, so concurrent moves validate against committed structure. The tree for navigation, paths, direct document counts and descendant filtering is built from one owner-scoped query.

Only leaf folders can be removed. Active and trashed documents are reparented to the removed folder's parent, or to the inbox for a root; their file paths, content, processing status and trash state are unchanged. The parent relation uses RESTRICT to protect direct folder deletion while allowing an entire owner cascade. Folder moves retain UUIDs and move descendants through their existing relations; they do not touch physical originals or previews.

The library defaults to direct-folder documents. `recursive=1` expands the selected folder filter to its owner-scoped descendants, including itself, before applying search, state, type and pagination. Sidebar counts remain direct counts. Complete paths distinguish same-name folders in upload and document move controls. Breadcrumbs and child tiles allow mobile navigation where the sidebar tree is hidden.

Migration 0002 preserves all existing folders as roots and leaves document associations and metadata intact. Back up the full data directory before upgrading; rollback to the old global name constraint is unsupported once duplicate names are used in different parents.

## Verified acceptance paths

- Text/PDF/image upload -> queued document -> worker -> searchable text and unmodified source.
- Foreign user -> document/page/file/thumbnail/mutation/search/status -> no access to the other owner's document.
- Foreign folder assignment and malformed folder ID -> 404.
- Invalid file / unsupported type / oversized file -> rejected before writing originals.
- OCR unavailable -> failed state -> manual retry -> successful processing.
- Trash -> hidden from active library -> restore -> downloadable original.
- Delete during processing -> lease invalidation -> discarded late result.
- Stale processing lease -> rescheduled task.
- Mutations require POST and CSRF protection.
- Existing single-level database -> upgraded roots and unchanged document metadata.
- Nested create -> rename/move subtree -> recursive search -> original bytes unchanged.
- Self/descendant/foreign parent or too-deep move -> rejection without partial update.
- Leaf removal -> active and trashed documents in parent; parent removal with children -> rejection.

## Deferred work

Sharing, NAS indexing, automatic backup, scalable search and Linux/Docker deployment are separate milestones. Folder names organize database entries; they do not rename the original directory hierarchy.
