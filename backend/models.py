from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)

from sqlalchemy.orm import relationship

from database import Base


def utc_now():
    return datetime.now(timezone.utc)


# ============================================================
# USER
# ============================================================

class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    username = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    email = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash = Column(
        String(255),
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    conversations = relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    settings = relationship(
        "UserSettings",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )

    feedback_items = relationship(
        "Feedback",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    memories = relationship(
        "UserMemory",
        back_populates="user",
        cascade="all, delete-orphan",
    )


# ============================================================
# CONVERSATION
# ============================================================

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    title = Column(
        String(120),
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )

    user = relationship(
        "User",
        back_populates="conversations",
    )

    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.id",
    )

    active_file = relationship(
        "ConversationFile",
        back_populates="conversation",
        cascade="all, delete-orphan",
        uselist=False,
    )


# ============================================================
# CONVERSATION FILE
# ============================================================

class ConversationFile(Base):
    __tablename__ = "conversation_files"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id"),
        nullable=False,
        unique=True,
        index=True,
    )

    original_filename = Column(
        String(255),
        nullable=False,
    )

    stored_path = Column(
        Text,
        nullable=False,
    )

    size_bytes = Column(
        Integer,
        nullable=False,
    )

    uploaded_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    conversation = relationship(
        "Conversation",
        back_populates="active_file",
    )

    content_record = relationship(
        "ConversationFileContent",
        back_populates="file",
        cascade="all, delete-orphan",
        uselist=False,
    )


# ============================================================
# CONVERSATION FILE CONTENT
# ============================================================

class ConversationFileContent(Base):
    __tablename__ = "conversation_file_contents"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    conversation_file_id = Column(
        Integer,
        ForeignKey("conversation_files.id"),
        nullable=False,
        unique=True,
        index=True,
    )

    content_text = Column(
        Text,
        nullable=False,
    )

    file = relationship(
        "ConversationFile",
        back_populates="content_record",
    )


# ============================================================
# MESSAGE
# ============================================================

class Message(Base):
    __tablename__ = "messages"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )

    role = Column(
        String(20),
        nullable=False,
    )

    content = Column(
        Text,
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    conversation = relationship(
        "Conversation",
        back_populates="messages",
    )


# ============================================================
# USER SETTINGS
# ============================================================

class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
        index=True,
    )

    theme = Column(
        String(20),
        default="light",
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="settings",
    )


# ============================================================
# FEEDBACK
# ============================================================

class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    type = Column(
        String(20),
        nullable=False,
    )

    message = Column(
        Text,
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="feedback_items",
    )

# ============================================================
# USER MEMORY
# ============================================================

class UserMemory(Base):
    __tablename__ = "user_memories"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    key = Column(
        String(80),
        default="note",
        nullable=False,
        index=True,
    )

    value = Column(
        Text,
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="memories",
    )

