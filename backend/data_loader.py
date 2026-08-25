"""
Loads and prepares all source data for the agent:
1. PDF documents -> parsed, chunked, tagged with authority metadata
2. xlsx sheets -> pandas DataFrames with parsed datetimes

Run this file directly to sanity-check loading before wiring it into the agent.
"""

import os
import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
from pypdf import PdfReader

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# Fixed dataset snapshot time (from the xlsx README sheet).
# All "is this late / has this been X hours" calculations are relative to this,
# NOT to the real current time, since this is a static assessment dataset.
DATASET_SNAPSHOT = datetime(2026, 8, 16, 11, 0)


# ---------------------------------------------------------------------------
# Document metadata / authority ranking
# ---------------------------------------------------------------------------
# authority_rank: lower number = higher authority
#   1 = signed customer agreement (only applies within its account_scope)
#   2 = current policy / SOP
#   3 = current product documentation
#   None = deprecated / excluded from default retrieval

DOC_METADATA = {
    "01_Support_Policy_v3_CURRENT.pdf": {
        "doc_type": "support_policy",
        "status": "CURRENT",
        "authority_rank": 2,
        "account_scope": None,
    },
    "02_Support_Policy_v2_DEPRECATED.pdf": {
        "doc_type": "support_policy",
        "status": "DEPRECATED",
        "authority_rank": None,
        "account_scope": None,
    },
    "03_Cancellation_and_Service_Credit_SOP_v4.pdf": {
        "doc_type": "sop",
        "status": "CURRENT",
        "authority_rank": 2,
        "account_scope": None,
    },
    "04_Product_Operations_Guide_and_Known_Issues.pdf": {
        "doc_type": "product_doc",
        "status": "CURRENT",
        "authority_rank": 3,
        "account_scope": None,
    },
    "05_Northstar_Logistics_Enterprise_Agreement.pdf": {
        "doc_type": "contract",
        "status": "CURRENT",
        "authority_rank": 1,
        "account_scope": "ACCT-001",
    },
    "06_LumenWorks_Service_Agreement.pdf": {
        "doc_type": "contract",
        "status": "CURRENT",
        "authority_rank": 1,
        "account_scope": "ACCT-002",
    },
}


@dataclass
class DocChunk:
    chunk_id: str
    source_file: str
    text: str
    doc_type: str
    status: str
    authority_rank: Optional[int]
    account_scope: Optional[str]


def _extract_pdf_text(path: str) -> str:
    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    raw = "\n".join(pages)
    # pypdf sometimes extracts one word per line depending on the PDF's
    # internal layout. Collapse all whitespace runs (including newlines)
    # into single spaces so text reads normally before we re-chunk it.
    return re.sub(r"\s+", " ", raw).strip()


def _chunk_text(text: str, max_chars: int = 700) -> list[str]:
    """
    Splits normalized (whitespace-collapsed) text on numbered section
    headers like "1. Order cancellation", "2. Failed-pickup credits".
    Falls back to hard-wrapping anything still too long.
    """
    # Split right before a numbered heading: space + digit + ". " + capital letter
    parts = re.split(r"(?=\d\.\s[A-Z])", text)
    chunks = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part) <= max_chars:
            chunks.append(part)
        else:
            for i in range(0, len(part), max_chars):
                chunks.append(part[i:i + max_chars])
    return chunks


def load_documents() -> list[DocChunk]:
    """Parses every PDF in DOC_METADATA into tagged, chunked text."""
    all_chunks: list[DocChunk] = []

    for filename, meta in DOC_METADATA.items():
        path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(path):
            print(f"[data_loader] WARNING: missing file {filename}, skipping")
            continue

        raw_text = _extract_pdf_text(path)
        text_chunks = _chunk_text(raw_text)

        for idx, chunk_text in enumerate(text_chunks):
            all_chunks.append(DocChunk(
                chunk_id=f"{filename}::chunk{idx}",
                source_file=filename,
                text=chunk_text,
                doc_type=meta["doc_type"],
                status=meta["status"],
                authority_rank=meta["authority_rank"],
                account_scope=meta["account_scope"],
            ))

    return all_chunks


# ---------------------------------------------------------------------------
# Structured data (xlsx)
# ---------------------------------------------------------------------------

DATETIME_COLUMNS = {
    "orders": [
        "booked_at", "pickup_window_start", "pickup_window_end",
        "pickup_actual_at", "cancellation_requested_at",
    ],
    "tickets": ["created_at", "last_customer_message_at"],
}


def load_structured_data() -> dict[str, pd.DataFrame]:
    """Loads accounts, orders, and tickets sheets into DataFrames with parsed datetimes."""
    xlsx_path = os.path.join(DATA_DIR, "ParcelPilot_Assessment_Data.xlsx")
    if not os.path.exists(xlsx_path):
        raise FileNotFoundError(f"Expected {xlsx_path} — copy the xlsx into data/")

    sheets = pd.read_excel(xlsx_path, sheet_name=["accounts", "orders", "tickets"])

    for sheet_name, cols in DATETIME_COLUMNS.items():
        df = sheets[sheet_name]
        for col in cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")

    return sheets


# ---------------------------------------------------------------------------
# Manual sanity check: run this file directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Loading documents ===")
    chunks = load_documents()
    print(f"Loaded {len(chunks)} chunks from {len(DOC_METADATA)} documents\n")
    for c in chunks[:3]:
        print(f"[{c.source_file}] rank={c.authority_rank} scope={c.account_scope}")
        print(c.text[:150].replace("\n", " "), "...\n")

    print("=== Loading structured data ===")
    data = load_structured_data()
    for name, df in data.items():
        print(f"\n--- {name} ({len(df)} rows) ---")
        print(df.head())