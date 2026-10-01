from datetime import datetime, timezone

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    status,
)

from fastapi.middleware.cors import CORSMiddleware

from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


from agent import get_ai_response

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
    Feedback,
    Message,
    User,
    UserSettings,
)

from schemas import (
    ChatRequest,
    FeedbackRequest,
    LoginRequest,
    SignupRequest,
    ThemeUpdateRequest,
)


# ============================================================
# DATABASE
# ============================================================

Base.metadata.create_all(bind=engine)


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

    db.delete(conversation)
    db.commit()

    return {
        "deleted": True,
        "conversation_id": conversation_id,
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

    # --------------------------------
    # GET OR CREATE CONVERSATION
    # --------------------------------

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

    try:
        ai_response = (
            get_ai_response(
                ai_context
            )
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
    }


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