# DevPilot Security Notes

## Python code execution

**Python execution is disabled unconditionally in this build.** The tool returns `PYTHON_EXECUTION_DISABLED`; the former `DEVPILOT_ENABLE_UNSANDBOXED_PYTHON` environment-variable escape hatch has been removed. AST checks are not a sandbox, and running user-provided code inside the API process could expose local files, secrets, network access, and the backend service account.

Before enabling execution for users, implement and review an OS/container-isolated runner with no secrets, no network by default, a minimal/read-only filesystem, a non-privileged identity, CPU/memory/process limits, and a strict wall-clock timeout. Containerization alone is not sufficient unless permissions and resource limits are configured correctly.

## File workspace and uploads

Uploads accept supported developer text/code files only, are limited to 2 MiB, and must decode as UTF-8. Filenames are normalized across Windows/POSIX path separators. The database is the source of truth for attachment text; optional workspace copies are scoped by user and conversation. Workspace cleanup handles symlinks before regular files/directories. File-reading tools require an active attachment and validate workspace containment, extension, and size.

Project ZIP uploads are inspected in memory and never extracted. The analyzer enforces archive/entry/content limits and skips traversal paths, symlinks, dependency/build folders, binaries, secret filenames, and oversized files. Common secret-like lines are redacted heuristically; this cannot guarantee that every credential is removed, so users should remove secrets before uploading archives.

## API guardrails

- Protected routes require a valid bearer token and scope conversations, memories, and files to the authenticated user.
- CORS origins are configurable through `CORS_ORIGINS` and default to local Vite development origins.
- `MAX_REQUEST_BYTES` controls a request `Content-Length` cap (default 16 MiB). Upload handlers also enforce their own tighter size bounds. A reverse proxy should independently enforce body-size limits for chunked/streamed requests.
- Sensitive routes have lightweight per-process rate limits. These limits are not shared across workers or machines; public deployments should use a shared limiter/API gateway and a reverse proxy.
- Baseline `X-Content-Type-Options`, `X-Frame-Options`, and `Referrer-Policy` headers are added to normal responses.
- `/api/admin/feedback` is available only to accounts whose email appears in the comma-separated `ADMIN_EMAILS` environment variable. Keep this variable private and configure only trusted administrators.

## Secrets and local data

Keep `.env` out of version control. Never include real API keys, JWT secrets, databases containing user data, virtual environments, or `node_modules` in source archives. Use strong, unique `JWT_SECRET_KEY` values outside local development. Review logs and uploaded project archives for sensitive data before sharing them.

## Remaining production work

The application has unit and API integration coverage, but this does not prove production readiness. Before public deployment, perform a deployment-specific security review, configure a shared rate limiter/reverse proxy, install dependencies and run frontend build/lint, verify provider credentials/quotas, and test the exact production origin and database backup/restore process.
