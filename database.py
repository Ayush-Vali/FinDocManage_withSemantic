from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timezone

DATABASE_URL = "sqlite:///./app.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
    # SQLite only allows one thread by default.
    # FastAPI uses multiple threads, so we disable that restriction.
)

SessionLocal = sessionmaker(bind=engine)
Base         = declarative_base()

#  TABLE: users

class UserDB(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    username      = Column(String,  unique=True, nullable=False)
    email         = Column(String,  unique=True, nullable=False)
    password_hash = Column(String,  nullable=False)

    role_assignments = relationship("UserRoleDB", back_populates="user")
    documents        = relationship("DocumentDB",  back_populates="uploader")

#  TABLE: roles

class RoleDB(Base):
    __tablename__ = "roles"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String,  unique=True, nullable=False)
    # ^ e.g. "Admin", "Analyst", "Auditor", "Client"

    permissions = Column(String, nullable=False)
    # ^ comma-separated string, e.g. "upload,view,edit", to be updated in FUTURE

    user_assignments = relationship("UserRoleDB", back_populates="role")



#  TABLE: user_roles

class UserRoleDB(Base):
    __tablename__ = "user_roles"

    id      = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)

    user = relationship("UserDB", back_populates="role_assignments")
    role = relationship("RoleDB", back_populates="user_assignments")


#  TABLE: documents

class DocumentDB(Base):
    __tablename__ = "documents"

    document_id   = Column(Integer,  primary_key=True, autoincrement=True)

    title         = Column(String,   nullable=False)
    company_name  = Column(String,   nullable=False)
    document_type = Column(String,   nullable=False)   # invoice | report | contract
    content       = Column(Text,     nullable=False)   # full document text
    uploaded_by   = Column(Integer,  ForeignKey("users.id"))
    created_at    = Column(DateTime, default=datetime.now(timezone.utc))

    uploader = relationship("UserDB", back_populates="documents")


# ─────────────────────────────────────────────────────────────────
#  CREATE ALL TABLES
# ─────────────────────────────────────────────────────────────────

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db          # hand the session to the route
    finally:
        db.close()        # always close, even if the route threw an error