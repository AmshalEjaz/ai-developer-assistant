from datetime import datetime, timezone
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from schemas import (
    ChatRequest,
    ConversationRenameRequest,
    FeedbackRequest,
    LoginRequest,
    MemoryCreateRequest,
    SignupRequest,
    ThemeUpdateRequest,
)
from fastapi.middleware.cors import CORSMiddleware

from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


from agent import get_ai_response
from groq_usage import get_groq_usage_snapshot
from memory import classify_memory_text, extract_explicit_memory
from file_workspace import (
    allowed_upload_filename,
    conversation_workspace,
    delete_conversation_workspace,
    save_active_file,
)
from tools import MAX_UPLOAD_BYTES

from auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

from database import (
    Base,
    engine,
    get_db,
)

from models import (
    Conversation,
    ConversationFile,
    ConversationFileContent,
    Feedback,
    Message,
    User,
    UserMemory,
    UserSettings,
)

from schemas import (
    ChatRequest,
    FeedbackRequest,
    LoginRequest,
    MemoryCreateRequest,
    SignupRequest,
    ThemeUpdateRequest,
)


# ============================================================
# DATABASE / WORKSPACE
# ============================================================

Base.metadata.create_all(bind=engine)

_workspace_root_raw = os.getenv("WORKSPACE_ROOT")
WORKSPACE_ROOT = (
    Path(_workspace_root_raw).expanduser().resolve()
    if _workspace_root_raw
    else None
)


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="DevPilot API",
    description="AI Developer Assistant Backend",
    version="2.0.0",
)


security = HTTPBearer(
    auto_error=False
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def serialize_datetime(value):
    if not value:
        return None

    return value.isoformat()


def serialize_conversation(
    conversation: Conversation,
):
    return {
        "id":
            conversation.id,

        "title":
            conversation.title,

        "created_at":
            serialize_datetime(
                conversation.created_at
            ),

        "updated_at":
            serialize_datetime(
                conversation.updated_at
            ),
    }


def serialize_message(
    message: Message,
):
    return {
        "id":
            message.id,

        "role":
            message.role,

        "content":
            message.content,

        "created_at":
            serialize_datetime(
                message.created_at
            ),
    }


def serialize_memory(
    memory: UserMemory,
):
    return {
        "id": memory.id,
        "key": memory.key,
        "value": memory.value,
        "created_at": serialize_datetime(memory.created_at),
        "updated_at": serialize_datetime(memory.updated_at),
    }


def serialize_attachment(
    attachment: ConversationFile | None,
):
    if not attachment:
        return None

    return {
        "id": attachment.id,
        "conversation_id": attachment.conversation_id,
        "filename": attachment.original_filename,
        "size_bytes": attachment.size_bytes,
        "uploaded_at": serialize_datetime(attachment.uploaded_at),
    }


def attachment_absolute_path(
    attachment: ConversationFile | None,
) -> Path | None:
    if not attachment or not WORKSPACE_ROOT:
        return None

    stored_path = str(attachment.stored_path or "")
    if stored_path.startswith("db://"):
        return None

    root = WORKSPACE_ROOT.resolve()
    candidate = (root / stored_path).resolve()

    try:
        candidate.relative_to(root)
    except ValueError:
        return None

    return candidate


def tool_context_for_conversation(
    conversation: Conversation,
) -> dict:
    attachment = conversation.active_file
    if not attachment:
        return {}

    if attachment.content_record is not None:
        return {
            "active_file_name": attachment.original_filename,
            "active_file_content": attachment.content_record.content_text,
        }

    path = attachment_absolute_path(attachment)
    if not path:
        return {}

    return {
        "workspace_path": str(path.parent),
        "active_file_path": str(path),
        "active_file_name": attachment.original_filename,
    }


def get_memories_for_user(
    db: Session,
    user_id: int,
):
    return (
        db.query(UserMemory)
        .filter(UserMemory.user_id == user_id)
        .order_by(UserMemory.updated_at.desc(), UserMemory.id.desc())
        .all()
    )


def save_memory_for_user(
    db: Session,
    user_id: int,
    memory_data: dict[str, str],
):
    key = memory_data["key"]
    value = memory_data["value"].strip()

    if key != "note":
        existing = (
            db.query(UserMemory)
            .filter(
                UserMemory.user_id == user_id,
                UserMemory.key == key,
            )
            .first()
        )

        if existing:
            existing.value = value
            existing.updated_at = utc_now()
            db.commit()
            db.refresh(existing)
            return existing

    duplicate = (
        db.query(UserMemory)
        .filter(
            UserMemory.user_id == user_id,
            UserMemory.value == value,
        )
        .first()
    )

    if duplicate:
        duplicate.updated_at = utc_now()
        db.commit()
        db.refresh(duplicate)
        return duplicate

    if (
        db.query(UserMemory)
        .filter(UserMemory.user_id == user_id)
        .count()
        >= 50
    ):
        raise HTTPException(
            status_code=400,
            detail="Memory limit reached. Delete an old memory before adding another.",
        )

    memory = UserMemory(
        user_id=user_id,
        key=key,
        value=value,
        created_at=utc_now(),
        updated_at=utc_now(),
    )

    db.add(memory)
    db.commit()
    db.refresh(memory)
    return memory


def create_conversation_title(
    message: str,
) -> str:

    clean = " ".join(
        message.split()
    )

    if len(clean) <= 60:
        return clean

    return (
        clean[:57].rstrip()
        + "..."
    )


def require_user(
    credentials:
        HTTPAuthorizationCredentials
        = Depends(security),

    db:
        Session
        = Depends(get_db),
) -> User:

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    try:
        user_id = decode_access_token(
            credentials.credentials
        )

    except ValueError as error:
        raise HTTPException(
            status_code=401,
            detail=str(error),
        )

    user = db.get(
        User,
        user_id,
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User no longer exists",
        )

    return user


def get_user_settings(
    db: Session,
    user_id: int,
) -> UserSettings:

    settings = (
        db.query(UserSettings)
        .filter(
            UserSettings.user_id
            == user_id
        )
        .first()
    )

    if settings:
        return settings

    settings = UserSettings(
        user_id=user_id,
        theme="light",
        updated_at=utc_now(),
    )

    db.add(settings)
    db.commit()
    db.refresh(settings)

    return settings


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():

    return {
        "message":
            "DevPilot backend is running",

        "status":
            "ok",
    }


@app.get("/api/health")
def health_check():

    return {
        "status": "healthy"
    }


# ============================================================
# SIGNUP
# ============================================================

@app.post(
    "/api/auth/signup",
    status_code=status.HTTP_201_CREATED,
)
def signup(
    request: SignupRequest,
    db: Session = Depends(get_db),
):

    email = (
        str(request.email)
        .strip()
        .lower()
    )

    username = (
        request.username
        .strip()
    )

    existing_email = (
        db.query(User)
        .filter(
            User.email == email
        )
        .first()
    )

    if existing_email:
        raise HTTPException(
            status_code=409,
            detail=(
                "Email is already registered"
            ),
        )

    existing_username = (
        db.query(User)
        .filter(
            User.username
            == username
        )
        .first()
    )

    if existing_username:
        raise HTTPException(
            status_code=409,
            detail=(
                "Username is already taken"
            ),
        )

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(
            request.password
        ),
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail=(
                "User with this email "
                "or username already exists"
            ),
        )

    # Create default settings
    get_user_settings(
        db,
        user.id,
    )

    return {
        "message":
            "Account created successfully",

        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
        },
    }


# ============================================================
# LOGIN
# ============================================================

@app.post("/api/auth/login")
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
):

    email = (
        str(request.email)
        .strip()
        .lower()
    )

    user = (
        db.query(User)
        .filter(
            User.email == email
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail=(
                "Invalid email or password"
            ),
        )

    if not verify_password(
        request.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Invalid email or password"
            ),
        )

    access_token = (
        create_access_token(
            user.id
        )
    )

    return {
        "access_token":
            access_token,

        "token_type":
            "bearer",

        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
        },
    }


# ============================================================
# CURRENT USER
# ============================================================

@app.get("/api/auth/me")
def get_current_user(
    current_user:
        User
        = Depends(require_user),
):

    return {
        "id":
            current_user.id,

        "username":
            current_user.username,

        "email":
            current_user.email,
    }


# ============================================================
# CONVERSATIONS
# ============================================================

@app.get("/api/conversations")
def list_conversations(
    current_user:
        User
        = Depends(require_user),

    db:
        Session
        = Depends(get_db),
):

    conversations = (
        db.query(Conversation)
        .filter(
            Conversation.user_id
            == current_user.id
        )
        .order_by(
            Conversation.updated_at.desc(),
            Conversation.id.desc(),
        )
        .all()
    )

    return {
        "conversations": [
            serialize_conversation(
                conversation
            )
            for conversation
            in conversations
        ]
    }


@app.get(
    "/api/conversations/{conversation_id}"
)
def get_conversation(
    conversation_id: int,

    current_user:
        User
        = Depends(require_user),

    db:
        Session
        = Depends(get_db),
):

    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id
            == conversation_id,

            Conversation.user_id
            == current_user.id,
        )
        .first()
    )

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail=(
                "Conversation not found"
            ),
        )

    messages = (
        db.query(Message)
        .filter(
            Message.conversation_id
            == conversation.id
        )
        .order_by(
            Message.id.asc()
        )
        .all()
    )

    return {
        "conversation":
            serialize_conversation(
                conversation
            ),

        "messages": [
            serialize_message(message)
            for message
            in messages
        ],

        "attachment":
            serialize_attachment(
                conversation.active_file
            ),
    }

@app.patch(
    "/api/conversations/{conversation_id}"
)
def rename_conversation(
    conversation_id: int,
    request: ConversationRenameRequest,

    current_user:
        User
        = Depends(require_user),

    db:
        Session
        = Depends(get_db),
):

    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id
            == conversation_id,

            Conversation.user_id
            == current_user.id,
        )
        .first()
    )

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    clean_title = (
        request.title
        .strip()
    )

    if not clean_title:
        raise HTTPException(
            status_code=400,
            detail="Chat title cannot be empty",
        )

    conversation.title = (
        clean_title[:80]
    )

    conversation.updated_at = (
        utc_now()
    )

    db.commit()
    db.refresh(conversation)

    return {
        "conversation":
            serialize_conversation(
                conversation
            )
    }

    
@app.delete(
    "/api/conversations/{conversation_id}"
)
def delete_conversation(
    conversation_id: int,

    current_user:
        User
        = Depends(require_user),

    db:
        Session
        = Depends(get_db),
):

    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id
            == conversation_id,

            Conversation.user_id
            == current_user.id,
        )
        .first()
    )

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail=(
                "Conversation not found"
            ),
        )

    if WORKSPACE_ROOT:
        try:
            delete_conversation_workspace(
                WORKSPACE_ROOT,
                user_id=current_user.id,
                conversation_id=conversation.id,
            )
        except OSError:
            pass

    db.delete(conversation)
    db.commit()

    return {
        "deleted": True,
        "conversation_id": conversation_id,
    }


# ============================================================
# CONVERSATION FILES
# ============================================================

@app.post("/api/files")
async def upload_conversation_file(
    file: UploadFile = File(...),
    conversation_id: int | None = Form(default=None),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    filename = Path(file.filename or "").name
    if not allowed_upload_filename(filename):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload a developer code/text file only.",
        )

    if conversation_id:
        conversation = (
            db.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.user_id == current_user.id,
            )
            .first()
        )
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conversation = Conversation(
            user_id=current_user.id,
            title="New Chat",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 2 MB limit.")

    try:
        content_text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Uploaded developer files must be UTF-8 text.",
        )

    # Database is the source of truth. The workspace copy is optional so a
    # Windows path/permission problem never prevents a valid upload.
    stored_path = f"db://conversation/{conversation.id}/{filename}"

    if WORKSPACE_ROOT:
        workspace = conversation_workspace(
            WORKSPACE_ROOT,
            user_id=current_user.id,
            conversation_id=conversation.id,
        )

        try:
            saved_path = save_active_file(workspace, filename, content)
            stored_path = (
                saved_path.resolve()
                .relative_to(WORKSPACE_ROOT.resolve())
                .as_posix()
            )
        except OSError:
            # Keep the database-backed attachment even if the optional local
            # workspace cannot be written.
            pass

    attachment = conversation.active_file

    if attachment:
        attachment.original_filename = filename
        attachment.stored_path = stored_path
        attachment.size_bytes = len(content)
        attachment.uploaded_at = utc_now()
    else:
        attachment = ConversationFile(
            conversation_id=conversation.id,
            original_filename=filename,
            stored_path=stored_path,
            size_bytes=len(content),
            uploaded_at=utc_now(),
        )
        db.add(attachment)
        db.flush()

    db.flush()

    content_record = attachment.content_record
    if content_record:
        content_record.content_text = content_text
    else:
        db.add(
            ConversationFileContent(
                conversation_file_id=attachment.id,
                content_text=content_text,
            )
        )

    conversation.updated_at = utc_now()
    db.commit()
    db.refresh(conversation)
    db.refresh(attachment)

    return {
        "conversation": serialize_conversation(conversation),
        "attachment": serialize_attachment(attachment),
    }


@app.delete("/api/conversations/{conversation_id}/file")
def delete_conversation_file(
    conversation_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    attachment = conversation.active_file
    if not attachment:
        return {"deleted": True, "conversation_id": conversation_id}

    path = attachment_absolute_path(attachment)
    if path:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            raise HTTPException(status_code=500, detail="Unable to remove the attached file.")

    db.delete(attachment)
    conversation.updated_at = utc_now()
    db.commit()

    return {"deleted": True, "conversation_id": conversation_id}


# ============================================================
# MEMORY
# ============================================================

@app.get("/api/memories")
def list_memories(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    memories = get_memories_for_user(db, current_user.id)

    return {
        "memories": [serialize_memory(memory) for memory in memories]
    }


@app.post(
    "/api/memories",
    status_code=status.HTTP_201_CREATED,
)
def create_memory(
    request: MemoryCreateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    memory_data = classify_memory_text(request.memory)

    if not memory_data:
        raise HTTPException(
            status_code=400,
            detail="Memory cannot be empty",
        )

    memory = save_memory_for_user(
        db,
        current_user.id,
        memory_data,
    )

    return {
        "memory": serialize_memory(memory),
        "message": "Memory saved.",
    }


@app.delete("/api/memories/{memory_id}")
def delete_memory(
    memory_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    memory = (
        db.query(UserMemory)
        .filter(
            UserMemory.id == memory_id,
            UserMemory.user_id == current_user.id,
        )
        .first()
    )

    if not memory:
        raise HTTPException(
            status_code=404,
            detail="Memory not found",
        )

    db.delete(memory)
    db.commit()

    return {
        "deleted": True,
        "memory_id": memory_id,
    }


# ============================================================
# CHAT
# ============================================================

@app.post("/api/chat")
def chat(
    request: ChatRequest,

    current_user:
        User
        = Depends(require_user),

    db:
        Session
        = Depends(get_db),
):

    user_text = (
        request.message
        .strip()
    )

    if not user_text:
        raise HTTPException(
            status_code=400,
            detail=(
                "Message cannot be empty"
            ),
        )

    memory_saved = None
    explicit_memory = extract_explicit_memory(user_text)

    if explicit_memory:
        memory_saved = save_memory_for_user(
            db,
            current_user.id,
            explicit_memory,
        )

    # --------------------------------
    # GET OR CREATE CONVERSATION
    # --------------------------------

    is_new_conversation = (
        request.conversation_id is None
    )

    if request.conversation_id:

        conversation = (
            db.query(Conversation)
            .filter(
                Conversation.id
                == request.conversation_id,

                Conversation.user_id
                == current_user.id,
            )
            .first()
        )

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Conversation not found"
                ),
            )

    else:

        conversation = Conversation(
            user_id=current_user.id,

            title=(
                create_conversation_title(
                    user_text
                )
            ),

            created_at=utc_now(),
            updated_at=utc_now(),
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    # --------------------------------
    # EXISTING CONTEXT
    # --------------------------------

    previous_messages = (
        db.query(Message)
        .filter(
            Message.conversation_id
            == conversation.id
        )
        .order_by(
            Message.id.asc()
        )
        .all()
    )

    is_new_conversation = (
        len(previous_messages) == 0
    )

    ai_context = [
        {
            "role": message.role,
            "content": message.content,
        }
        for message
        in previous_messages
    ]

    # --------------------------------
    # SAVE USER MESSAGE FIRST
    # --------------------------------

    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=user_text,
        created_at=utc_now(),
    )

    conversation.updated_at = (
        utc_now()
    )

    db.add(user_message)
    db.commit()
    db.refresh(user_message)
    db.refresh(conversation)

    ai_context.append(
        {
            "role": "user",
            "content": user_text,
        }
    )

    # --------------------------------
    # GROQ RESPONSE
    # --------------------------------

    memories = get_memories_for_user(
        db,
        current_user.id,
    )

    memory_context = [
        {
            "key": memory.key,
            "value": memory.value,
        }
        for memory in memories
    ]

    generated_title = None
    tool_context = tool_context_for_conversation(
        conversation
    )

    try:
        if is_new_conversation:
            (
                ai_response,
                generated_title,
            ) = get_ai_response(
                ai_context,
                memories=memory_context,
                include_chat_title=True,
                tool_context=tool_context,
            )
        else:
            ai_response = get_ai_response(
                ai_context,
                memories=memory_context,
                tool_context=tool_context,
            )

    except Exception:
        # User message stays saved.
        raise HTTPException(
            status_code=502,
            detail={
                "message": (
                    "DevPilot could not get an "
                    "AI response right now. "
                    "Please try again."
                ),

                "conversation":
                    serialize_conversation(
                        conversation
                    ),
            },
        )

    # --------------------------------
    # SAVE ASSISTANT MESSAGE
    # --------------------------------

    if (
        is_new_conversation
        and generated_title
    ):
        conversation.title = (
            generated_title
        )

    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=ai_response,
        created_at=utc_now(),
    )

    conversation.updated_at = (
        utc_now()
    )

    db.add(assistant_message)

    db.commit()

    db.refresh(
        assistant_message
    )

    db.refresh(
        conversation
    )

    return {
        "conversation":
            serialize_conversation(
                conversation
            ),

        "user_message":
            serialize_message(
                user_message
            ),

        "message":
            serialize_message(
                assistant_message
            ),

        "memory_saved": (
            serialize_memory(memory_saved)
            if memory_saved
            else None
        ),

        "attachment":
            serialize_attachment(
                conversation.active_file
            ),
    }


# ============================================================
# GROQ USAGE
# ============================================================

@app.get("/api/groq/usage")
def get_groq_usage(
    current_user:
        User
        = Depends(require_user),
):
    return get_groq_usage_snapshot()


# ============================================================
# SETTINGS
# ============================================================

@app.get("/api/settings")
def get_settings(
    current_user:
        User
        = Depends(require_user),

    db:
        Session
        = Depends(get_db),
):

    settings = (
        get_user_settings(
            db,
            current_user.id,
        )
    )

    return {
        "theme":
            settings.theme
    }


@app.put("/api/settings/theme")
def update_theme(
    request: ThemeUpdateRequest,

    current_user:
        User
        = Depends(require_user),

    db:
        Session
        = Depends(get_db),
):

    settings = (
        get_user_settings(
            db,
            current_user.id,
        )
    )

    settings.theme = (
        request.theme
    )

    settings.updated_at = (
        utc_now()
    )

    db.commit()
    db.refresh(settings)

    return {
        "theme":
            settings.theme
    }


# ============================================================
# FEEDBACK
# ============================================================

@app.post(
    "/api/feedback",
    status_code=status.HTTP_201_CREATED,
)
def create_feedback(
    request: FeedbackRequest,

    current_user:
        User
        = Depends(require_user),

    db:
        Session
        = Depends(get_db),
):

    message = (
        request.message
        .strip()
    )

    if not message:
        raise HTTPException(
            status_code=400,
            detail=(
                "Feedback message "
                "cannot be empty"
            ),
        )

    item = Feedback(
        user_id=current_user.id,
        type=request.type,
        message=message,
        created_at=utc_now(),
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    return {
        "message":
            "Thank you. Your message has been saved.",

        "feedback": {
            "id":
                item.id,

            "type":
                item.type,

            "created_at":
                serialize_datetime(
                    item.created_at
                ),
        },
    }