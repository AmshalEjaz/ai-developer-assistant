from typing import Literal

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    field_validator,
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

class SettingsPreferencesUpdateRequest(BaseModel):
    response_verbosity: Literal["concise", "balanced", "detailed"] = "balanced"
    preferred_stack: str = Field(default="", max_length=120)
    behavior_preferences: str = Field(default="", max_length=500)

    @field_validator("preferred_stack", "behavior_preferences", mode="before")
    @classmethod
    def trim_preference_text(cls, value):
        return value.strip() if isinstance(value, str) else value
