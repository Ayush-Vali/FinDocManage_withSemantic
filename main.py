from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db, UserDB, RoleDB, UserRoleDB, DocumentDB
from auth import hash_password, verify_password, create_jwt_token, get_current_user
from rag import index_document_content, remove_document_embeddings, semantic_search, get_document_chunks


class RegisterInput(BaseModel):
    username: str
    email:    str
    password: str

class LoginInput(BaseModel):
    username: str
    password: str

class RoleCreateInput(BaseModel):
    name:        str
    permissions: str

class AssignRoleInput(BaseModel):
    user_id: int
    role_id: int

class DocumentUploadInput(BaseModel):
    title:         str
    company_name:  str
    document_type: str
    content:       str

class RAGSearchInput(BaseModel):
    query: str
    top_k: int = 5


app = FastAPI(title="Financial Document Manager")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth ──────────────────────────────────────────────────────────

@app.post("/auth/register")
def register(data: RegisterInput, db: Session = Depends(get_db)):
    if db.query(UserDB).filter(UserDB.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already taken.")
    if db.query(UserDB).filter(UserDB.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered.")

    user = UserDB(username=data.username, email=data.email, password_hash=hash_password(data.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": f"User '{data.username}' registered!"}


@app.post("/auth/login")
def login(data: LoginInput, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.username == data.username).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong username or password.")

    return {
        "message":  "Login successful!",
        "token":    create_jwt_token(user.id, user.username),
        "username": user.username
    }


# ── Roles ─────────────────────────────────────────────────────────

@app.post("/roles/create")
def create_role(
    data:         RoleCreateInput,
    db:           Session = Depends(get_db),
    current_user: UserDB  = Depends(get_current_user)
):
    if db.query(RoleDB).filter(RoleDB.name == data.name).first():
        raise HTTPException(status_code=400, detail="Role already exists.")

    role = RoleDB(name=data.name, permissions=data.permissions)
    db.add(role)
    db.commit()
    db.refresh(role)
    return {"message": f"Role '{data.name}' created!", "role_id": role.id}


@app.post("/users/assign-role")
def assign_role(data: AssignRoleInput, db: Session = Depends(get_db), current_user: UserDB = Depends(get_current_user)):
    user = db.query(UserDB).filter(UserDB.id == data.user_id).first()
    role = db.query(RoleDB).filter(RoleDB.id == data.role_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")
    already = db.query(UserRoleDB).filter(UserRoleDB.user_id == data.user_id, UserRoleDB.role_id == data.role_id).first()
    if already:
        return {"message": "Role already assigned."}
    db.add(UserRoleDB(user_id=data.user_id, role_id=data.role_id))
    db.commit()
    return {"message": f"Role '{role.name}' assigned to '{user.username}'!"}


@app.get("/users/{user_id}/roles")
def get_user_roles(user_id: int, db: Session = Depends(get_db), current_user: UserDB = Depends(get_current_user)):
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"user": user.username, "roles": [{"role_id": ur.role.id, "role_name": ur.role.name} for ur in user.role_assignments]}


@app.get("/users/{user_id}/permissions")
def get_user_permissions(user_id: int, db: Session = Depends(get_db), current_user: UserDB = Depends(get_current_user)):
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    all_permissions = set()
    for ur in user.role_assignments:
        all_permissions.update(ur.role.permissions.split(","))
    return {"user": user.username, "permissions": list(all_permissions)}


# ── Documents ─────────────────────────────────────────────────────

@app.post("/documents/upload")
def upload_document(
    data:         DocumentUploadInput,
    db:           Session = Depends(get_db),
    current_user: UserDB  = Depends(get_current_user)
):
    doc = DocumentDB(
        title         = data.title,
        company_name  = data.company_name,
        document_type = data.document_type,
        content       = data.content,
        uploaded_by   = current_user.id
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    chunks_created = index_document_content(
        document_id   = doc.document_id,
        title         = doc.title,
        company_name  = doc.company_name,
        document_type = doc.document_type,
        content       = doc.content
    )
    return {
        "message":        "Document uploaded and indexed!",
        "document_id":    doc.document_id,
        "title":          doc.title,
        "chunks_created": chunks_created
    }


@app.get("/documents")
def get_all_documents(db: Session = Depends(get_db), current_user: UserDB = Depends(get_current_user)):
    docs = db.query(DocumentDB).all()
    return [
        {
            "document_id":   d.document_id,
            "title":         d.title,
            "company_name":  d.company_name,
            "document_type": d.document_type,
            "uploaded_by":   d.uploader.username if d.uploader else "?",
            "created_at":    d.created_at.isoformat()
        }
        for d in docs
    ]


# !! CRITICAL: /documents/search MUST come before /documents/{document_id}
# FastAPI matches routes top-to-bottom. If /{document_id} is first,
# the word "search" gets captured as a document_id and the wrong route runs.
@app.get("/documents/search")
def search_documents(
    company_name:  str | None = None,
    document_type: str | None = None,
    db:            Session = Depends(get_db),
    current_user:  UserDB  = Depends(get_current_user)
):
    query = db.query(DocumentDB)
    if company_name:
        query = query.filter(DocumentDB.company_name.ilike(f"%{company_name}%"))
    if document_type:
        query = query.filter(DocumentDB.document_type == document_type)
    return [
        {
            "document_id":   d.document_id,
            "title":         d.title,
            "company_name":  d.company_name,
            "document_type": d.document_type,
            "uploaded_by":   d.uploader.username if d.uploader else "?",
            "created_at":    d.created_at.isoformat()
        }
        for d in query.all()
    ]


@app.get("/documents/{document_id}")
def get_document(document_id: int, db: Session = Depends(get_db), current_user: UserDB = Depends(get_current_user)):
    doc = db.query(DocumentDB).filter(DocumentDB.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {
        "document_id":   doc.document_id,
        "title":         doc.title,
        "company_name":  doc.company_name,
        "document_type": doc.document_type,
        "content":       doc.content,
        "uploaded_by":   doc.uploader.username if doc.uploader else "?",
        "created_at":    doc.created_at.isoformat()
    }


@app.delete("/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db), current_user: UserDB = Depends(get_current_user)):
    doc = db.query(DocumentDB).filter(DocumentDB.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    title = doc.title
    db.delete(doc)
    db.commit()
    removed = remove_document_embeddings(document_id)
    return {"message": f"'{title}' deleted.", "chunks_removed": removed}


# ── RAG ───────────────────────────────────────────────────────────

@app.post("/rag/index-document")
def reindex_document(
    document_id:  int,
    db:           Session = Depends(get_db),
    current_user: UserDB  = Depends(get_current_user)
):
    doc = db.query(DocumentDB).filter(DocumentDB.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    remove_document_embeddings(document_id)
    chunks_created = index_document_content(
        document_id=doc.document_id, title=doc.title,
        company_name=doc.company_name, document_type=doc.document_type, content=doc.content
    )
    return {"message": f"'{doc.title}' re-indexed.", "chunks_created": chunks_created}


@app.delete("/rag/remove-document/{document_id}")
def remove_embeddings_route(document_id: int, current_user: UserDB = Depends(get_current_user)):
    removed = remove_document_embeddings(document_id)
    if removed == 0:
        raise HTTPException(status_code=404, detail="No embeddings found for this document.")
    return {"message": f"Removed {removed} chunks.", "chunks_removed": removed}


@app.post("/rag/search")
def rag_search(data: RAGSearchInput, current_user: UserDB = Depends(get_current_user)):
    results = semantic_search(query=data.query, top_k=data.top_k)
    return {"query": data.query, "results": results}


@app.get("/rag/context/{document_id}")
def get_context(document_id: int, current_user: UserDB = Depends(get_current_user)):
    chunks = get_document_chunks(document_id)
    if not chunks:
        raise HTTPException(status_code=404, detail="No chunks found for this document.")
    return {"document_id": document_id, "total_chunks": len(chunks), "chunks": chunks}