from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


# ============================================================
# DATABASE PATH
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATABASE_FILE = BASE_DIR / "devpilot.db"

DATABASE_URL = f"sqlite:///{DATABASE_FILE}"


# ============================================================
# DATABASE ENGINE
# ============================================================

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False
    },
)


# ============================================================
# DATABASE SESSION
# ============================================================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# ============================================================
# BASE MODEL
# ============================================================

Base = declarative_base()


# ============================================================
# DATABASE DEPENDENCY
# ============================================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()