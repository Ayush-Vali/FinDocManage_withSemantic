from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from sentence_transformers import CrossEncoder

CHROMA_PATH     = "./chroma_db"
COLLECTION_NAME = "financial_docs"

splitter = RecursiveCharacterTextSplitter(
    chunk_size    = 1000,
    chunk_overlap = 150,
    separators    = ["\n\n", "\n", ". ", " ", ""]
)

embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

vector_store = Chroma(
    collection_name    = COLLECTION_NAME,
    embedding_function = embeddings,
    persist_directory  = CHROMA_PATH
)

retriever = vector_store.as_retriever(
    search_type   = "similarity",
    search_kwargs = {"k": 20}
)

reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


def index_document_content(document_id, title, company_name, document_type, content) -> int:
    doc_id = int(document_id)  # always store as int so where-filter type matches on retrieval
    docs = splitter.create_documents(
        texts     = [content],
        metadatas = [{"document_id": doc_id, "title": title,
                      "company_name": company_name, "document_type": document_type}]
    )
    for i, doc in enumerate(docs):
        doc.metadata["chunk_index"] = i

    ids = [f"{doc_id}_chunk_{i}" for i in range(len(docs))]
    vector_store.add_documents(documents=docs, ids=ids)
    return len(docs)


def remove_document_embeddings(document_id) -> int:
    doc_id = int(document_id)  # cast to int — must match the type stored in metadata
    result = vector_store.get(where={"document_id": doc_id})
    ids    = result.get("ids", [])
    if not ids:
        return 0
    vector_store.delete(ids=ids)
    return len(ids)


def semantic_search(query: str, top_k: int = 5) -> list[dict]:
    retrieved_docs = retriever.invoke(query)
    if not retrieved_docs:
        return []

    pairs  = [(query, doc.page_content) for doc in retrieved_docs]
    scores = reranker.predict(pairs).tolist()

    ranked = sorted(zip(retrieved_docs, scores), key=lambda x: x[1], reverse=True)[:top_k]

    return [
        {
            "chunk_text":    doc.page_content,
            "document_id":   doc.metadata.get("document_id"),
            "title":         doc.metadata.get("title"),
            "company_name":  doc.metadata.get("company_name"),
            "document_type": doc.metadata.get("document_type"),
            "chunk_index":   doc.metadata.get("chunk_index"),
            "rerank_score":  round(score, 4),
        }
        for doc, score in ranked
    ]


def get_document_chunks(document_id) -> list[dict]:
    doc_id = int(document_id)  # cast to int — must match the type stored in metadata
    result = vector_store.get(
        where   = {"document_id": doc_id},
        include = ["documents", "metadatas"]
    )
    ids       = result.get("ids", [])
    documents = result.get("documents", [])
    metadatas = result.get("metadatas", [])

    if not ids:
        return []

    combined = sorted(
        zip(ids, documents, metadatas),
        key=lambda x: x[2].get("chunk_index", 0)
    )
    return [
        {"chunk_id": cid, "chunk_index": meta.get("chunk_index"), "text": text}
        for cid, text, meta in combined
    ]