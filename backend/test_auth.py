import unittest
import uuid

from fastapi.testclient import TestClient

from auth import hash_password, verify_password
from database import SessionLocal
from main import app
from models import User


client = TestClient(app)


class TestAuthentication(unittest.TestCase):

    def setUp(self):
        unique = uuid.uuid4().hex[:8]

        self.username = f"user_{unique}"
        self.email = f"{unique}@example.com"
        self.password = "Password123!"

    def tearDown(self):
        db = SessionLocal()

        try:
            user = (
                db.query(User)
                .filter(User.email == self.email)
                .first()
            )

            if user:
                db.delete(user)
                db.commit()

        finally:
            db.close()

    def test_signup_creates_user(self):
        response = client.post(
            "/api/auth/signup",
            json={
                "username": self.username,
                "email": self.email,
                "password": self.password,
            },
        )

        self.assertEqual(response.status_code, 201)

        db = SessionLocal()

        try:
            user = (
                db.query(User)
                .filter(User.email == self.email)
                .first()
            )

            self.assertIsNotNone(user)
            self.assertNotEqual(
                user.password_hash,
                self.password,
            )

            self.assertTrue(
                verify_password(
                    self.password,
                    user.password_hash,
                )
            )

        finally:
            db.close()

    def test_login_returns_token(self):
        db = SessionLocal()

        try:
            user = User(
                username=self.username,
                email=self.email,
                password_hash=hash_password(
                    self.password
                ),
            )

            db.add(user)
            db.commit()

        finally:
            db.close()

        response = client.post(
            "/api/auth/login",
            json={
                "email": self.email,
                "password": self.password,
            },
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertIn("access_token", data)
        self.assertEqual(
            data["token_type"],
            "bearer",
        )

    def test_me_returns_logged_in_user(self):
        db = SessionLocal()

        try:
            user = User(
                username=self.username,
                email=self.email,
                password_hash=hash_password(
                    self.password
                ),
            )

            db.add(user)
            db.commit()

        finally:
            db.close()

        login_response = client.post(
            "/api/auth/login",
            json={
                "email": self.email,
                "password": self.password,
            },
        )

        token = login_response.json()["access_token"]

        response = client.get(
            "/api/auth/me",
            headers={
                "Authorization": f"Bearer {token}"
            },
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(
            data["username"],
            self.username,
        )

        self.assertEqual(
            data["email"],
            self.email,
        )


if __name__ == "__main__":
    unittest.main()