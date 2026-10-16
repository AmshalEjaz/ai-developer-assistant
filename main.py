from datetime import datetime, timezone
import os
import zipfile
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
from history_retrieval import retrieve_history_context
from project_zip import inspect_project_zip, select_relevant_project_context, MAX_ARCHIVE_BYTES
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
    ConversationProjectContext,
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
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


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


@app.get("/api/conversations/search")
def search_conversations(
    q: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    query = " ".join(str(q or "").split()).strip()[:120]
    if len(query) < 2:
        return {"results": []}

    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(500)
        .all()
    )
    if not conversations:
        return {"results": []}

    # This search is intentionally headline/title-only: users expect the
    # sidebar search to find a conversation by its displayed chat title.
    # Keep it local to the database; it must never call an AI provider.
    needle = query.casefold()
    results = []
    for conversation in conversations:
        title = str(conversation.title or "")
        if needle in title.casefold():
            results.append({
                **serialize_conversation(conversation),
                "snippet": title,
            })
        if len(results) >= 50:
            break
    return {"results": results, "query": query}


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


@app.get("/api/history/last-activity")
def last_history_activity(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    conversation = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .first()
    )
    latest_message = None
    if conversation:
        latest_message = (
            db.query(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .filter(Conversation.user_id == current_user.id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .first()
        )
    return {
        "has_history": conversation is not None,
        "latest_conversation": serialize_conversation(conversation) if conversation else None,
        "latest_message_at": serialize_datetime(latest_message.created_at) if latest_message else None,
        "latest_message_role": latest_message.role if latest_message else None,
        "note": "These timestamps record saved chat activity, not necessarily the date source code was last edited.",
    }


@app.post("/api/project/analyze-zip")
async def analyze_project_zip(
    file: UploadFile = File(...),
    question: str = Form(...),
    conversation_id: int | None = Form(default=None),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Please choose a .zip file.")
    question = " ".join(str(question or "").split()).strip()
    if not question:
        raise HTTPException(status_code=400, detail="Add a question about the project ZIP.")
    if len(question) > 4000:
        raise HTTPException(status_code=400, detail="Question is too long (maximum 4,000 characters).")

    raw = await file.read(MAX_ARCHIVE_BYTES + 1)
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise HTTPException(status_code=413, detail="ZIP exceeds the 15 MB upload limit.")
    try:
        inspection = inspect_project_zip(raw, question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if conversation_id:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
            .first()
        )
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found.")
    else:
        conversation = Conversation(
            user_id=current_user.id,
            title=create_conversation_title(question),
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=f"[Project ZIP: {filename}] {question}",
        created_at=utc_now(),
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    file_sections = []
    for item in inspection["files"]:
        file_sections.append(f"FILE: {item['path']}\n```\n{item['content']}\n```")
    project_context = (
        f"User uploaded project archive {filename}. Only {inspection['file_count']} selected, "
        f"bounded text files are included ({inspection['characters_sent']} characters total); "
        "dependencies, binaries, secret files, and most generated files were skipped. "
        "The ZIP was inspected in memory and never extracted. Do not claim to have inspected files "
        "that are not listed below.\n\n" + "\n\n---\n\n".join(file_sections)
    )
    saved_context = conversation.project_context
    if saved_context:
        saved_context.archive_name = filename
        saved_context.context_text = project_context
        saved_context.file_count = inspection["file_count"]
        saved_context.characters_sent = inspection["characters_sent"]
        saved_context.created_at = utc_now()
    else:
        db.add(ConversationProjectContext(
            conversation_id=conversation.id,
            archive_name=filename,
            context_text=project_context,
            file_count=inspection["file_count"],
            characters_sent=inspection["characters_sent"],
            created_at=utc_now(),
        ))
    db.commit()
    memories = get_memories_for_user(db, current_user.id)
    memory_context = [{"key": item.key, "value": item.value} for item in memories]
    try:
        answer = get_ai_response(
            [{"role": "user", "content": question}],
            memories=memory_context,
            project_context=select_relevant_project_context(project_context, question),
        )
        if isinstance(answer, tuple):
            answer = answer[0]
    except Exception as exc:
        import logging
        logging.getLogger("devpilot.ai").exception(
            "Project ZIP analysis failed (%s)", type(exc).__name__
        )
        raise HTTPException(
            status_code=502,
            detail="DevPilot could not analyze the ZIP with Groq or Gemini. Your question was saved; check backend logs and provider quotas, then retry.",
        )

    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=str(answer),
        created_at=utc_now(),
    )
    conversation.updated_at = utc_now()
    db.add(assistant_message)
    db.commit()
    db.refresh(conversation)
    db.refresh(assistant_message)
    db.refresh(user_message)
    return {
        "conversation": serialize_conversation(conversation),
        "user_message": serialize_message(user_message),
        "message": serialize_message(assistant_message),
        "analysis": {
            "files_considered": [item["path"] for item in inspection["files"]],
            "file_count": inspection["file_count"],
            "characters_sent": inspection["characters_sent"],
            "skipped_count": inspection["skipped_count"],
        },
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

    # Search this user's older saved chats for relevant context. The active
    # conversation is excluded, and the retriever enforces user ownership.
    history_context = retrieve_history_context(
        db,
        current_user.id,
        user_text,
        exclude_conversation_id=conversation.id,
    )

    generated_title = None
    tool_context = tool_context_for_conversation(
        conversation
    )
    saved_project_context = (
        select_relevant_project_context(
            conversation.project_context.context_text,
            user_text,
        )
        if conversation.project_context
        else None
    )

    try:
        # Use the same provider request path for new and existing chats.
        # Previously, a new chat used a special title-generation prompt and
        # expected a tuple response, while existing chats used a plain string.
        # Keep title creation local (create_conversation_title above) so a title
        # formatting/parsing issue cannot break the very first assistant reply.
        ai_response = get_ai_response(
            ai_context,
            memories=memory_context,
            history_context=history_context,
            tool_context=tool_context,
            project_context=saved_project_context,
        )
        if isinstance(ai_response, tuple):
            ai_response = ai_response[0]
        ai_response = str(ai_response or "").strip()
        if not ai_response:
            raise RuntimeError("AI providers returned an empty response.")

    except Exception as exc:
        # Keep the user-facing error generic, but log the real cause locally
        # so provider quota/configuration problems can be diagnosed.
        import logging
        logging.getLogger("devpilot.ai").exception(
            "All configured AI providers failed (%s)",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": (
                    "DevPilot could not get an AI response from Groq or Gemini. "
                    "Check backend logs and provider quotas, then try again."
                ),
                "conversation": serialize_conversation(conversation),
            },
        )

    # --------------------------------
    # SAVE ASSISTANT MESSAGE
    # --------------------------------

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