DevPilot historical chat recall fix

This patch only changes the backend historical-recall matcher and retrieval selection.
It does not change the database schema, saved-memory limit, UI, .env, or provider settings.

Before applying, back up these two files:
  backend/memory.py
  backend/history_retrieval.py

Then replace them with the files in this ZIP and restart the FastAPI backend.

What it improves:
- Recognizes more English/Roman Urdu recall phrasing (including "yaad ma", "kal wali chat", and "maine ... bataya").
- Prioritizes messages matching the question, even when they are older than the last 8 messages in a conversation.
- Keeps the existing per-user isolation and bounded context limits.

Important: This cannot retrieve a message that was never saved, is outside the current scan limits, or does not match any searchable term. Verify using a detail you know is present in a saved old chat. Do not overwrite the whole project ZIP.
