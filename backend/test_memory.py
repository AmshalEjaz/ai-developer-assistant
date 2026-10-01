import sys
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

# Keep these tests self-contained in the sandbox.
fake_groq = types.ModuleType("groq")
class _FakeGroq:
    def __init__(self, *args, **kwargs):
        pass
fake_groq.Groq = _FakeGroq
sys.modules.setdefault("groq", fake_groq)

fake_bcrypt = types.ModuleType("bcrypt")
fake_bcrypt.hashpw = lambda *args, **kwargs: b"unused"
fake_bcrypt.gensalt = lambda: b"unused"
fake_bcrypt.checkpw = lambda *args, **kwargs: True
sys.modules.setdefault("bcrypt", fake_bcrypt)

fake_jwt = types.ModuleType("jwt")
class _ExpiredSignatureError(Exception):
    pass
class _InvalidTokenError(Exception):
    pass
fake_jwt.ExpiredSignatureError = _ExpiredSignatureError
fake_jwt.InvalidTokenError = _InvalidTokenError
fake_jwt.encode = lambda *args, **kwargs: "unused"
fake_jwt.decode = lambda *args, **kwargs: {"sub": "1"}
sys.modules.setdefault("jwt", fake_jwt)

from fastapi.testclient import TestClient

from database import SessionLocal
from main import app, require_user
from models import User


client = TestClient(app)


class TestMemoryFeature(unittest.TestCase):
    def setUp(self):
        self.user_ids = []

    def tearDown(self):
        app.dependency_overrides.clear()
        db = SessionLocal()
        try:
            for user_id in self.user_ids:
                user = db.get(User, user_id)
                if user:
                    db.delete(user)
            db.commit()
        finally:
            db.close()

    def create_user(self):
        unique = uuid.uuid4().hex[:10]
        db = SessionLocal()
        try:
            user = User(
                username=f"memory_{unique}",
                email=f"memory_{unique}@example.com",
                password_hash="unused",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            self.user_ids.append(user.id)
            return user.id
        finally:
            db.close()

    def authenticate_as(self, user_id):
        def current_user_override():
            db = SessionLocal()
            try:
                user = db.get(User, user_id)
                db.expunge(user)
                return user
            finally:
                db.close()
        app.dependency_overrides[require_user] = current_user_override

    def test_user_can_add_list_and_delete_memory(self):
        user_id = self.create_user()
        self.authenticate_as(user_id)

        created = client.post(
            "/api/memories",
            json={"memory": "Prefer concise answers."},
        )
        self.assertEqual(created.status_code, 201)
        memory = created.json()["memory"]
        self.assertEqual(memory["value"], "Prefer concise answers.")

        listed = client.get("/api/memories")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["memories"]), 1)

        deleted = client.delete(f"/api/memories/{memory['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["deleted"], True)

        listed_again = client.get("/api/memories")
        self.assertEqual(listed_again.json()["memories"], [])

    def test_memories_are_isolated_per_user(self):
        first_user = self.create_user()
        second_user = self.create_user()

        self.authenticate_as(first_user)
        created = client.post(
            "/api/memories",
            json={"memory": "Use Roman Urdu."},
        )
        self.assertEqual(created.status_code, 201)

        self.authenticate_as(second_user)
        listed = client.get("/api/memories")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["memories"], [])

        forbidden_delete = client.delete(
            f"/api/memories/{created.json()['memory']['id']}"
        )
        self.assertEqual(forbidden_delete.status_code, 404)

    @patch("main.get_ai_response", return_value="Theek hai, yaad rahe ga.")
    def test_explicit_memory_command_is_saved_and_injected_into_chat(self, mock_ai):
        user_id = self.create_user()
        self.authenticate_as(user_id)

        response = client.post(
            "/api/chat",
            json={
                "message": "Mujhy hamesha Roman Urdu me reply krna yaad rakhna"
            },
        )
        self.assertEqual(response.status_code, 200)

        _, kwargs = mock_ai.call_args
        self.assertIn("memories", kwargs)
        self.assertTrue(
            any(
                "Roman Urdu" in memory["value"]
                for memory in kwargs["memories"]
            )
        )

        saved = client.get("/api/memories")
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(
            any(
                "Roman Urdu" in memory["value"]
                for memory in saved.json()["memories"]
            )
        )

    def test_agent_prompt_explicitly_protects_roman_urdu_script(self):
        source = Path(__file__).with_name("agent.py").read_text(encoding="utf-8")
        self.assertIn("Roman Urdu", source)
        self.assertIn("Devanagari", source)
        self.assertIn("same language", source)


if __name__ == "__main__":
    unittest.main()
