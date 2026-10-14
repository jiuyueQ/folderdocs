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

## Deferred work

Nested folders, sharing, NAS indexing, automatic backup, scalable search and Linux/Docker deployment are separate milestones. Folder names currently organize database entries; they do not rename the original directory hierarchy.
