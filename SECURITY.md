# DevPilot Security Notes

## Python code execution

DevPilot's Python tool runs snippets in a subprocess and applies AST checks, a timeout, isolated Python mode, and output limits. These checks are defense-in-depth only. **They do not create a secure sandbox**: Python object-model escape techniques and operating-system behavior make in-process/AST restrictions insufficient for untrusted code.

For safety, Python execution is disabled by default. The tool returns `PYTHON_EXECUTION_DISABLED` unless the operator sets `DEVPILOT_ENABLE_UNSANDBOXED_PYTHON=1` (or `true`/`yes`). Enabling this setting permits code to run with the backend process's operating-system privileges and should only be considered for trusted, local development. Do not enable it for public deployments or untrusted users.

Before enabling user-submitted execution in a deployed service, run snippets inside a separately configured OS/container sandbox with no secrets, no network by default, read-only/minimal filesystem access, a non-privileged identity, memory/CPU/process limits, and a strict wall-clock timeout. Containerization alone is not sufficient unless its permissions and resource limits are configured appropriately.

## File workspace

Uploaded files are restricted by extension and size. Workspace cleanup handles symlinks before regular files/directories to avoid following symlink targets while clearing the active-file area. Keep workspace roots private and ensure only the backend service account can modify them.

## Secrets

Keep `.env` out of archives and version control. Never include API keys, JWT secrets, database files containing user data, virtual environments, or `node_modules` in a source ZIP. Use `.env.example` with placeholder values for setup documentation.

## Project ZIP analysis

ZIP uploads are read in memory and are not extracted to disk. The analyzer enforces archive, entry-count, and uncompressed-size limits; skips path traversal paths, symlinks, dependency/build folders, binaries, secret filenames, and oversized files; and redacts common secret-like lines. The saved project snapshot contains only selected, sanitized text snippets. Each Groq request receives a smaller query-relevant subset. Secret detection is heuristic, not guaranteed; users should still remove credentials from project archives before uploading. Do not expose the API publicly without additional request rate limiting and deployment hardening.
