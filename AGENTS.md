# Development

Before starting a new implementation session, ask the user to choose Windows or Linux. An environment choice already made for the active session remains valid. The current implementation is Windows native.

Use Python for application logic. Preserve document originals, scope every document and folder query to its owner, and run permission and processing tests before release. Do not commit user files, databases, secrets, or local runtime state.

## Code Review Rules

These rules apply to code reviews. Reviewing an existing PR does not start a new implementation session or require a Windows/Linux choice. Read `docs/ARCHITECTURE.md` for current contracts and `docs/PR_REVIEW.md` for the review workflow.

- Preserve private, owner-scoped access across document/folder queries, search, status, preview, download, thumbnail and mutation routes. Reject foreign folder assignments; keep media behind authenticated routes and mutations protected by POST and CSRF. Flag a concrete route or request that bypasses these boundaries. Sharing is deferred: an intentional sharing feature must define and test its authorization boundary.
- Preserve uploaded originals and recoverable trash. OCR may write derived text/previews only; a late worker result must not resurrect a trashed/deleted document or retain its preview. Check conditional task claims, lease invalidation, completion/failure updates and stale-task recovery together. Permanent deletion must remain restricted to trash and handle Windows file locks without losing the recoverable record on failure.
- Preserve the documented local Windows runtime unless the PR explicitly changes that contract: bind to loopback by default, respect `FOLDERDOCS_DATA_DIR`, prevent duplicate service instances for the same data directory, and clean up only the launcher's own process trees. Validate uploads before saving originals and keep processing limits bounded. Flag committed uploads, databases, secrets, demo credentials or runtime artifacts; a deliberate contract/limit change needs corresponding documentation and validation.

Report actionable issues introduced by the PR with a precise location, trigger, impact and evidence. Compare the stated requirement with the diff and related callers; distinguish intentional, validated behavior changes from regressions. Keep style preferences optional. State which checks actually ran and which were skipped; do not equate mocked OCR with native OCR verification.
