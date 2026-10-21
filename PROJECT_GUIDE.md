# DevPilot Project Guide

This guide supplements the existing README. The README files have not been changed.

## Architecture

- `frontend/`: React 19 application built with Vite; includes authentication, chat history, attachment UI, themes, settings, saved memories, and feedback forms.
- `backend/main.py`: FastAPI routes, authentication dependencies, conversation/file endpoints, per-user settings, feedback, request guardrails, and SQLite persistence.
- `backend/agent.py`: Groq-first assistant orchestration, bounded conversation context, tool calling, and Gemini fallback.
- `backend/tools.py`: code analysis, bounded attached-file reading, documentation search, and a fail-closed Python execution tool.
- `backend/project_zip.py`: bounded in-memory ZIP inspection; archives are not extracted.
- `backend/history_retrieval.py` and `backend/memory.py`: user-scoped historical conversation retrieval and explicit persistent memories.
- `backend/models.py` / `backend/database.py`: SQLAlchemy models and local SQLite database.

## Local setup

1. Create and activate a Python virtual environment.
2. Install backend packages with `python -m pip install -r backend/requirements.txt`.
3. Create a local `backend/.env` file with provider credentials and a strong JWT secret. Never commit real secrets.
4. Start the backend from `backend/` with `python -m uvicorn main:app --reload`.
5. In another terminal, run `npm ci` from `frontend/`, then `npm run dev`.
6. For frontend checks, run `node --test ui_regression.test.mjs`, `npm run lint`, and `npm run build` from `frontend/` after dependencies are installed.
7. For backend tests, run `python -m pytest -v` from `backend/`.

## Environment variables

- `GROQ_API_KEY`: primary AI provider key.
- `GEMINI_API_KEY` (or `GOOGLE_API_KEY`): optional Gemini fallback key.
- `JWT_SECRET_KEY`: required strong secret used to sign login tokens.
- `CORS_ORIGINS`: comma-separated allowed browser origins; defaults to local Vite origins.
- `MAX_REQUEST_BYTES`: request body cap in bytes; defaults to 16 MiB.
- `WORKSPACE_ROOT`: optional private directory for per-user/per-conversation active file copies.
- `ADMIN_EMAILS`: comma-separated email addresses authorized to access `/api/admin/feedback`.
- `SERPER_API_KEY`: optional live documentation search provider key.

## Settings and personalization

Settings are scoped to the logged-in user and stored in SQLite. Theme, response verbosity (`concise`, `balanced`, `detailed`), preferred programming stack, and additional behavior preferences are restored from `/api/settings`. Preference text is bounded and is passed to both primary and fallback AI providers as guidance, not as a security policy.

## Security controls and limitations

- Authenticated endpoints enforce user ownership for conversations, memories, and uploaded files.
- File uploads are limited to supported text/code extensions, 2 MiB, and valid UTF-8. ZIP project analysis has separate archive and content bounds.
- CORS origins are configurable. The API applies a content-length cap, lightweight per-process rate limits on sensitive routes, and baseline response security headers.
- Rate limiting is process-local and is not a substitute for a shared limiter/API gateway in a multi-worker or public deployment. Content-length limits should also be enforced at the reverse proxy.
- Python execution always returns `PYTHON_EXECUTION_DISABLED`. The old environment-variable escape hatch has been removed; do not enable execution until an OS/container sandbox adapter has been designed and reviewed.
- ZIP secret redaction is heuristic and cannot guarantee all credentials are removed. Avoid uploading archives containing secrets.
- Provider keys, database files, `.env`, virtual environments, and `node_modules` must not be distributed in source archives.

## API notes

- `GET /api/settings` returns the signed-in user's settings.
- `PUT /api/settings/preferences` updates response verbosity, preferred stack, and behavior preferences.
- `PUT /api/settings/theme` updates the theme.
- `GET /api/admin/feedback` returns recent feedback only when the signed-in email is present in `ADMIN_EMAILS`; otherwise it returns `403`.
- Provider errors are surfaced to the API as a generic `502` response while backend logs retain provider failure types for diagnosis.

## Verification status for this build

Backend tests and the frontend's Node-based UI regression tests are included. A frontend production build and ESLint run require installing the pinned npm dependencies; if the package registry is unavailable, those two checks remain unverified rather than being treated as passed.


## Docker Compose (local self-hosted setup)

Docker support is provided by `docker-compose.yml` plus the backend/frontend Dockerfiles. Copy `backend/.env.example` to `backend/.env`, set real local credentials and a strong `JWT_SECRET_KEY`, then run `docker compose up --build`. The frontend is published on `http://localhost:5173` and the API on `http://localhost:8000`; SQLite and workspace data persist in the `devpilot_data` volume. Stop with `docker compose down`; the named volume remains unless explicitly removed. Docker itself was not available in the build environment, so the compose build has not been executed here. For remote hosting, set `VITE_API_URL` to the reachable HTTPS API origin and configure `CORS_ORIGINS` to the exact frontend origin before building; production TLS, secret management, backups, shared rate limiting, and deployment-specific security review are still required.
