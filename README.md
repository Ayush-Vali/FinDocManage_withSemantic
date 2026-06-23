# Financial Document Manager

A FastAPI application for managing financial documents with AI-powered semantic search. Organisations can store, retrieve, and search across invoices, reports, and contracts using meaning-based retrieval rather than keyword matching.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI |
| Database | SQLite via SQLAlchemy |
| Authentication | JWT (PyJWT) |
| Text Splitting | LangChain `RecursiveCharacterTextSplitter` |
| Embeddings | `all-MiniLM-L6-v2` via LangChain HuggingFaceEmbeddings |
| Vector Store | ChromaDB via LangChain |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` via sentence-transformers |
| Frontend | Vanilla HTML/CSS/JS |

---

## Project Structure

```
financial_app/
│
├── main.py          # All API routes
├── database.py      # SQLAlchemy models and DB session
├── auth.py          # JWT creation, decoding, password hashing
├── rag.py           # LangChain splitter, Chroma vector store, retriever, reranker
│
├── login.html       # Login / Register page
├── index.html       # Main dashboard (protected)
│
└── requirements.txt
```

---

## Setup

**1. Install dependencies**

```bash
pip install -r requirements.txt
```

**2. Start the server**

```bash
uvicorn main:app --reload
```

**3. Open the app**

Open `login.html` in your browser. The dashboard (`index.html`) is only accessible after login.

Interactive API docs are available at `http://127.0.0.1:8000/docs`.

---

## Database Schema

```
users                   roles                   user_roles
────────────────        ────────────────        ────────────────
id (PK)                 id (PK)                 id (PK)
username (unique)       name (unique)           user_id → users.id
email (unique)          permissions             role_id → roles.id
password_hash

documents
──────────────────────────────
document_id (PK, autoincrement)
title
company_name
document_type              (invoice | report | contract)
content
uploaded_by → users.id
created_at
```

---

## How JWT Authentication Works

```
Browser                             Server
  │                                   │
  │  POST /auth/login                 │
  │  { username, password }  ──────►  │
  │                                   │  1. Find user in DB
  │                                   │  2. Compare password hashes
  │                                   │  3. Sign a JWT token
  │                                   │     payload: { user_id, username, exp }
  │  { token: "xxxxx.yyyyy.zzzzz" }  ◄──  │
  │                                   │
  │  (saved in sessionStorage)        │
  │                                   │
  │  GET /documents                   │
  │  Authorization: Bearer xxxxx ──►  │
  │                                   │  1. Read token from header
  │                                   │  2. Verify signature with SECRET_KEY
  │                                   │  3. Decode user_id from payload
  │                                   │  4. Attach user to request
  │  [ list of documents ]           ◄──  │
```

The token expires after 24 hours. No session is stored on the server — the token itself carries the user identity.

---

## Semantic Search Workflow

```
POST /rag/search  { "query": "...", "top_k": 5 }
        │
        ▼
  Embed the query
  (same model: all-MiniLM-L6-v2)
        │
        ▼
  ChromaDB vector similarity search
  retriever.invoke(query)  →  top 20 closest chunks
        │
        ▼
  CrossEncoder reranker  (ms-marco-MiniLM-L-6-v2)
  scores each (query, chunk) pair more accurately
        │
        ▼
  Sort by rerank score descending
  return top_k results
```

---

## API Reference

### Auth

| Method | Endpoint | Body | Description |
|---|---|---|---|
| POST | `/auth/register` | `{ username, email, password }` | Create account |
| POST | `/auth/login` | `{ username, password }` | Returns JWT token |

### Roles

| Method | Endpoint | Body / Params | Description |
|---|---|---|---|
| POST | `/roles/create` | `{ name, permissions }` | Create a role |
| POST | `/users/assign-role` | `{ user_id, role_id }` | Assign role to user by name |
| GET | `/users/{id}/roles` | `{ user_id }` | See user's roles |
| GET | `/users/{id}/permissions` | `{ user_id }` | See user's permissions |



### Documents

| Method | Endpoint | Description |
|---|---|---|
| POST | `/documents/upload` | Upload document and auto-index into ChromaDB |
| GET | `/documents` | List all documents (metadata only) |
| GET | `/documents/{document_id}` | Get one document with full content |
| DELETE | `/documents/{document_id}` | Delete from SQLite and remove embeddings from ChromaDB |
| GET | `/documents/search?company_name=X&document_type=Y` | SQL metadata filter search |

### RAG

| Method | Endpoint | Description |
|---|---|---|
| POST | `/rag/search` | Semantic search across all indexed documents |
| GET | `/rag/context/{document_id}` | View all stored chunks for a document |
| POST | `/rag/index-document?document_id=N` | Re-index a document (refresh embeddings) |
| DELETE | `/rag/remove-document/{document_id}` | Remove embeddings from ChromaDB only |
