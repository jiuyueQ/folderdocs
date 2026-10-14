# Local validation

Verified on Windows with Python 3.14.6, Django 5.2.18 and Tesseract 5.5.3.

- 12 Django tests pass with real OCR enabled. Coverage includes private document/file/thumbnail access, cross-user mutations and search, folder ownership, malformed IDs, file validation, source integrity, text and PDF processing, actual image and scanned PDF OCR, failure retry, stale lease recovery, deletion during processing, trash/restore/purge, CSRF and pagination.
- Browser integration passes on Microsoft Edge through Playwright: login, folder creation, upload, worker completion, rename, content search, original download, trash, restore, permanent deletion and folder removal.
- Desktop screenshots captured at 1440 px width. Mobile screenshot captured at 390 px width, with no horizontal overflow.
- The native Windows launcher starts both Waitress and the worker; sample documents are synthetic. Credentials and user data are excluded from Git.

The Windows/Ubuntu GitHub Actions matrix is configured, but remote CI results are available only after the repository is published. OCR accuracy varies with document quality; handwriting recognition is not an acceptance criterion.
