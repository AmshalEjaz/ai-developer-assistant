import sys
import types
import unittest
import uuid
from unittest.mock import patch

# The sandbox lacks some optional runtime packages. Stub imports only; these
# tests override authentication and mock the AI provider, so none are executed.
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
from models import Conversation, Message, User


client = TestClient(app)


class TestConversationDelete(unittest.TestCase):
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
                username=f"user_{unique}",
                email=f"{unique}@example.com",
                password_hash="unused",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            user_id = user.id
            self.user_ids.append(user_id)
            return user_id
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

    @patch("main.get_ai_response", return_value="Saved reply")
    def test_owner_can_delete_conversation_and_messages(self, _mock_ai):
        owner_id = self.create_user()
        self.authenticate_as(owner_id)

        created = client.post(
            "/api/chat",
            json={"message": "Delete this conversation"},
        )
        self.assertEqual(created.status_code, 200)
        conversation_id = created.json()["conversation"]["id"]

        response = client.delete(f"/api/conversations/{conversation_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"deleted": True, "conversation_id": conversation_id},
        )

        db = SessionLocal()
        try:
            self.assertIsNone(db.get(Conversation, conversation_id))
            self.assertEqual(
                db.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .count(),
                0,
            )
        finally:
            db.close()

    @patch("main.get_ai_response", return_value="Private reply")
    def test_user_cannot_delete_another_users_conversation(self, _mock_ai):
        owner_id = self.create_user()
        other_id = self.create_user()

        self.authenticate_as(owner_id)
        created = client.post(
            "/api/chat",
            json={"message": "Owner only"},
        )
        conversation_id = created.json()["conversation"]["id"]

        self.authenticate_as(other_id)
        response = client.delete(f"/api/conversations/{conversation_id}")
        self.assertEqual(response.status_code, 404)

        self.authenticate_as(owner_id)
        detail = client.get(f"/api/conversations/{conversation_id}")
        self.assertEqual(detail.status_code, 200)


if __name__ == "__main__":
    unittest.main()
