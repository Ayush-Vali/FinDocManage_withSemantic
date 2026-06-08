"""
database.py
───────────
Everything related to the SQL database lives here:
  - Engine setup (which database file to use)
  - Table definitions (each class = one table)
  - SessionLocal (the factory that creates DB connections)

Other files import from here. Nothing else.
"""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import uuid

# ─────────────────────────────────────────────────────────────────
#  ENGINE + SESSION
#
#  engine       = the actual connection to the SQLite file
#  SessionLocal = a factory; call SessionLocal() to open a session
#  Base         = all our model classes inherit from this
# ─────────────────────────────────────────────────────────────────

DATABASE_URL = "sqlite:///./app.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
    # ↑ SQLite only allows one thread by default.
    #   FastAPI uses multiple threads, so we disable that restriction.
)

SessionLocal = sessionmaker(bind=engine)
Base         = declarative_base()


# ─────────────────────────────────────────────────────────────────
#  TABLE: users
# ─────────────────────────────────────────────────────────────────

class UserDB(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    username      = Column(String,  unique=True, nullable=False)
    email         = Column(String,  unique=True, nullable=False)
    password_hash = Column(String,  nullable=False)
    # ^ We NEVER store the plain password.
    #   Only its sha256 hash. Even if the DB leaks,
    #   nobody can reverse the hash back to the password.

    # One user → many role assignments (via the junction table)
    role_assignments = relationship("UserRoleDB", back_populates="user")
    # One user → many documents they uploaded
    documents        = relationship("DocumentDB",  back_populates="uploader")


# ─────────────────────────────────────────────────────────────────
#  TABLE: roles
# ─────────────────────────────────────────────────────────────────

class RoleDB(Base):
    __tablename__ = "roles"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String,  unique=True, nullable=False)
    # ^ e.g. "Admin", "Analyst", "Auditor", "Client"

    permissions = Column(String, nullable=False)
    # ^ comma-separated string, e.g. "upload,view,edit"
    #   Simple approach — in a real app you'd have a permissions table.

    user_assignments = relationship("UserRoleDB", back_populates="role")


# ─────────────────────────────────────────────────────────────────
#  TABLE: user_roles  (junction / many-to-many)
#
#  Why a separate table?
#    A user can have MANY roles. A role can belong to MANY users.
#    You can't store that in either the users or roles table alone.
#    The junction table holds pairs: (user_id, role_id).
#
#    user_id=1, role_id=2  →  user 1 has role 2
#    user_id=1, role_id=3  →  user 1 also has role 3
# ─────────────────────────────────────────────────────────────────

class UserRoleDB(Base):
    __tablename__ = "user_roles"

    id      = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)

    user = relationship("UserDB", back_populates="role_assignments")
    role = relationship("RoleDB", back_populates="user_assignments")


# ─────────────────────────────────────────────────────────────────
#  TABLE: documents
# ─────────────────────────────────────────────────────────────────

class DocumentDB(Base):
    __tablename__ = "documents"

    document_id   = Column(Integer,  primary_key=True, autoincrement=True)

    title         = Column(String,   nullable=False)
    company_name  = Column(String,   nullable=False)
    document_type = Column(String,   nullable=False)   # invoice | report | contract
    content       = Column(Text,     nullable=False)   # full document text
    uploaded_by   = Column(Integer,  ForeignKey("users.id"))
    created_at    = Column(DateTime, default=datetime.utcnow)

    uploader = relationship("UserDB", back_populates="documents")


# ─────────────────────────────────────────────────────────────────
#  CREATE ALL TABLES
#  This runs when database.py is imported.
#  If the tables already exist, SQLAlchemy skips them (safe to re-run).
# ─────────────────────────────────────────────────────────────────

Base.metadata.create_all(bind=engine)


# ─────────────────────────────────────────────────────────────────
#  get_db()  —  FastAPI dependency
#
#  How FastAPI dependencies work:
#    Instead of opening/closing a DB session manually in every route,
#    we write this once and FastAPI injects it automatically.
#
#    @app.get("/something")
#    def my_route(db: Session = Depends(get_db)):
#        # db is already open here, will auto-close when done
#
#  The "yield" makes it a generator:
#    - Code BEFORE yield → runs before the route
#    - Code AFTER yield  → runs after the route (cleanup)
# ─────────────────────────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db          # hand the session to the route
    finally:
        db.close()        # always close, even if the route threw an error