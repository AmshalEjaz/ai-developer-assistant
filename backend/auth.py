import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from dotenv import load_dotenv


load_dotenv()


JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")

    hashed_password = bcrypt.hashpw(
        password_bytes,
        bcrypt.gensalt(),
    )

    return hashed_password.decode("utf-8")


def verify_password(
    password: str,
    password_hash: str,
) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int) -> str:
    if not JWT_SECRET_KEY:
        raise ValueError(
            "JWT_SECRET_KEY is missing from .env"
        )

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    )

    payload = {
        "sub": str(user_id),
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> int:
    if not JWT_SECRET_KEY:
        raise ValueError(
            "JWT_SECRET_KEY is missing from .env"
        )

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )

        user_id = payload.get("sub")

        if not user_id:
            raise ValueError(
                "Invalid authentication token"
            )

        return int(user_id)

    except jwt.ExpiredSignatureError:
        raise ValueError(
            "Authentication token has expired"
        )

    except jwt.InvalidTokenError:
        raise ValueError(
            "Invalid authentication token"
        )