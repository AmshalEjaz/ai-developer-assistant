from typing import Literal

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
)


class SignupRequest(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=50,
    )

    email: EmailStr

    password: str = Field(
        min_length=8,
        max_length=128,
    )


class LoginRequest(BaseModel):
    email: EmailStr

    password: str = Field(
        min_length=8,
        max_length=128,
    )


class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=20000,
    )

    conversation_id: int | None = Field(
        default=None,
        ge=1,
    )


class ThemeUpdateRequest(BaseModel):
    theme: Literal[
        "light",
        "dark",
    ]


class FeedbackRequest(BaseModel):
    type: Literal[
        "feedback",
        "problem",
    ]

    message: str = Field(
        min_length=3,
        max_length=5000,
    )

class MemoryCreateRequest(BaseModel):
    memory: str = Field(
        min_length=3,
        max_length=2000,
    )

class ConversationRenameRequest(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=80,
    )