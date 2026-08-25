"""
Document search tool: embeds and indexes the PDF chunks from data_loader,
and exposes a filtered semantic-search function for the agent.

Filtering rules enforced here (not just in the prompt):
- Deprecated docs excluded by default (only included if include_deprecated=True)
- Contract chunks are scoped: a query for account X will only retrieve
  X's own contract, never another account's contract
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings
from google import genai
from dotenv import load_dotenv

from data_loader import load_documents, DocChunk

load_dotenv()

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "chroma_db")
COLLECTION_NAME = "parcelpilot_docs"

_genai_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


class GeminiEmbeddingFunction(EmbeddingFunction):
    """
    Uses Gemini's embedding API instead of a local sentence-transformers model.
    This avoids pulling in PyTorch, which was causing out-of-memory crashes
    on Render's 512MB free tier.
    """
    def __call__(self, input: Documents) -> Embeddings:
        result = _genai_client.models.embed_content(
            model="gemini-embedding-001",
            contents=input,
        )
        return [e.values for e in result.embeddings]


_embed_fn = GeminiEmbeddingFunction()

_client = chromadb.PersistentClient(path=CHROMA_DIR)


def _get_or_build_collection():
    existing = [c.name for c in _client.list_collections()]
    if COLLECTION_NAME in existing:
        return _client.get_collection(COLLECTION_NAME, embedding_function=_embed_fn)

    collection = _client.create_collection(COLLECTION_NAME, embedding_function=_embed_fn)
    chunks: list[DocChunk] = load_documents()

    collection.add(
        ids=[c.chunk_id for c in chunks],
        documents=[c.text for c in chunks],
        metadatas=[{
            "source_file": c.source_file,
            "doc_type": c.doc_type,
            "status": c.status,
            "authority_rank": c.authority_rank if c.authority_rank is not None else -1,
            "account_scope": c.account_scope or "GLOBAL",
        } for c in chunks],
    )
    print(f"[document_search] Indexed {len(chunks)} chunks into Chroma.")
    return collection


_collection = _get_or_build_collection()


def search_documents(query: str, account_id: str | None = None,
                      include_deprecated: bool = False, top_k: int = 5) -> list[dict]:
    """
    Semantic search over policy/SOP/product docs + the caller's own contract
    (if account_id given). Never returns another account's contract chunks,
    and excludes deprecated docs unless explicitly requested.
    """
    where_conditions = []

    if not include_deprecated:
        where_conditions.append({"status": {"$ne": "DEPRECATED"}})

    # Scope: only this account's contract, OR global (non-contract) docs
    if account_id:
        where_conditions.append({
            "$or": [
                {"account_scope": account_id},
                {"account_scope": "GLOBAL"},
            ]
        })
    else:
        where_conditions.append({"account_scope": "GLOBAL"})

    where = {"$and": where_conditions} if len(where_conditions) > 1 else where_conditions[0]

    results = _collection.query(
        query_texts=[query],
        n_results=top_k,
        where=where,
    )

    output = []
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    for text, meta in zip(docs, metas):
        output.append({
            "text": text,
            "source_file": meta["source_file"],
            "doc_type": meta["doc_type"],
            "status": meta["status"],
            "authority_rank": meta["authority_rank"] if meta["authority_rank"] != -1 else None,
        })
    return output


if __name__ == "__main__":
    print("-- Query: 'cancellation fee' scoped to Northstar (ACCT-001) --")
    for r in search_documents("cancellation fee for booked shipment", account_id="ACCT-001"):
        print(f"[{r['source_file']}] rank={r['authority_rank']} :: {r['text'][:100]}...")

    print("\n-- Query: 'P1 response time' scoped to LumenWorks (ACCT-002) --")
    for r in search_documents("P1 first response time", account_id="ACCT-002"):
        print(f"[{r['source_file']}] rank={r['authority_rank']} :: {r['text'][:100]}...")

    print("\n-- Query: 'bulk upload row limit' no account scope --")
    for r in search_documents("bulk upload row limit known issue"):
        print(f"[{r['source_file']}] rank={r['authority_rank']} :: {r['text'][:100]}...")