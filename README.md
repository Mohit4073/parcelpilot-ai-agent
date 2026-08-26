# ParcelPilot Internal AI Support Assistant

An internal support/operations chatbot for ParcelPilot (a fictional logistics company), built as an AI agent that reasons over policy documents, contracts, and operational data using tool-calling — with a companion dashboard for proactive issue detection.

**Live demo:** https://parcelpilot-ai-agent-ten.vercel.app
**Backend API:** https://parcelpilot-ai-agent-5dkg.onrender.com

> Note: the backend is hosted on Render's free tier, which spins down after inactivity. The **first** request after idle time can take 30-50 seconds to respond — this is expected, not a bug.

---

## What this is

A ParcelPilot support agent (or manager) logs in and can ask questions like:
- *"Can Northstar cancel ORD-1001 without a cancellation fee?"*
- *"A production API key was posted in a public Slack channel, ticket TKT-505. What should we do?"*

The agent reasons across three tool categories — document search, structured data lookups/calculations, and mocked actions — and never executes an action without explicit user confirmation. A second tab shows a proactive dashboard flagging SLA breaches and recurring known-issue clusters.

## Why this scope

The assessment allowed choosing internal or customer-facing. I built the **internal support/operations chatbot**, because it exercises all three required tool types naturally and pairs directly with the "proactive issue detection" bonus problem in one cohesive product, rather than two disconnected halves.

## Architecture

```
Frontend (React + Vite)
   |
   |  fetch /login, /chat, /confirm-action, /dashboard
   v
Backend (FastAPI)
   - Session store (in-memory, keyed by session_id)
   - Agent orchestrator (Gemini function calling)
   |
   +-- Tool: search_documents   -> ChromaDB (Gemini embeddings) over 6 PDFs
   +-- Tool: structured data    -> pandas over ParcelPilot_Assessment_Data.xlsx
   +-- Tool: propose_action /   -> in-memory mocked action store,
       confirm_action              two-phase (draft -> explicit confirm)
```

## Tech stack

| Layer | Choice |
|---|---|
| LLM + tool calling | Google Gemini (`gemini-3.6-flash`), native function calling |
| Backend | FastAPI (Python) |
| Document search | ChromaDB, embedded with Gemini's `gemini-embedding-001` |
| Structured data | pandas over the provided xlsx (accounts/orders/tickets) |
| Actions | Mocked in-memory store, two-phase propose/confirm |
| Frontend | React (Vite) |
| Hosting | Render (backend), Vercel (frontend) |

## Source-of-truth / trust design

The six source documents intentionally conflict with each other. The system resolves this with an explicit precedence order, encoded directly in the agent's system instructions (mirroring what Support Policy v3 itself states):

1. **Signed customer agreement** (only applies to that specific account)
2. **Current support policy / SOP**
3. **Current product documentation**
4. Historical ticket resolutions are **never** treated as authoritative — they're excluded from being cited as policy, and the agent is instructed to actively contradict a wrong historical resolution if asked about it.

Additional trust behaviors:
- Deprecated documents (`Support Policy v2`) are excluded from retrieval by default, and never used unless the user explicitly asks for historical policy.
- Contract chunks are account-scoped at the retrieval layer — Northstar's contract is never surfaced for a LumenWorks question, and vice versa.
- The agent never promises a service credit when carrier fault or timing is ambiguous (per SOP v4 Section 3), and flags when a credit exceeds the ₹1,000 manager-approval threshold.
- All calculations (cancellation fees, service credits, SLA breach status) are computed by dedicated backend functions, never estimated by the LLM from raw dates — this keeps the numbers deterministic and auditable.

## Access control

Access control is enforced in the **tool layer**, not just prompted:
- Every backend tool call takes the logged-in user's context as a parameter and scopes data accordingly.
- Two mocked roles: `support_agent` and `manager`. Only a manager can confirm an action that grants a service credit above ₹1,000.
- The LLM can only ever *draft* an action (`propose_action`) — it has no code path to execute one. Only a direct, separate user click (`/confirm-action`) can confirm it.

## Proactive issue detection

The Dashboard tab uses simple, explainable rule-based logic (not a black-box model) over the same ticket data:
- **SLA breach detection**: compares each open ticket's elapsed time against its plan/contract's first-response target (contract overrides applied, e.g. Northstar's 15-minute P1 target).
- **Recurring known-issue clusters**: flags when ≥2 tickets match a documented known issue's symptoms (e.g. KI-208 bulk-upload failures appearing across multiple LumenWorks tickets).

Deterministic rules were chosen over ML clustering because they're explainable, testable against the fixed dataset, and appropriate for this data volume.

## Setup & running locally

### Prerequisites
- Python 3.10+
- Node.js 18+
- A free Gemini API key from [Google AI Studio](https://aistudio.google.com)

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```
Copy `.env.example` to `.env` and add your key:
```
GEMINI_API_KEY=your_actual_key_here
```
Run:
```bash
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173`. By default `frontend/src/api.js` points at the deployed Render backend — change `API_BASE` to `http://localhost:8000` for fully local development.

## Deployment

- **Backend** is deployed on Render as a Python web service (root directory `backend`, start command `uvicorn main:app --host 0.0.0.0 --port $PORT`), with `GEMINI_API_KEY` set as an environment variable in the Render dashboard.
- **Frontend** is deployed on Vercel (root directory `frontend`, Vite preset auto-detected).
- CORS on the backend allows any `*.vercel.app` subdomain matching this project via a regex, so preview deployments work without manual updates.

## Known limitations (by design, for this assessment's scope)

- **Sessions are in-memory** — they reset on backend restart. A production version would persist chat history and rebuild the agent's context per-request from a database.
- **Actions are mocked** — `propose_action`/`confirm_action` write to an in-memory store, not a real ticketing/escalation system.
- **Auth is mocked** — a role picker at login, not real authentication.
- **Render free-tier cold starts** — the backend sleeps after inactivity; first request after idle can take 30-50s.

## Example test scenarios

| Question | Tests |
|---|---|
| "Can Northstar cancel ORD-1001 without a fee?" | Contract override beats SOP |
| "LumenWorks wants to cancel ORD-2001, do they owe a fee?" | Same logic, opposite outcome (contract defers to SOP) |
| "API key exposed in Slack, ticket TKT-505" | P1 classification + escalation proposal + confirm flow |
| "TKT-504 still shows BOOKED after pickup" | Cross-referencing a known issue (KI-211) instead of guessing |
| "Bulk upload row limit, based on past tickets" | Ignoring a wrong historical ticket resolution |

## Project structure

```
parcelpilot-ai-agent/
├── backend/
│   ├── main.py                 # FastAPI app: /login, /chat, /confirm-action, /dashboard
│   ├── agent.py                 # Gemini agent orchestration, tool binding
│   ├── dashboard.py              # Proactive issue detection logic
│   ├── auth.py                  # Mocked users/roles
│   ├── data_loader.py           # Loads + chunks PDFs, loads xlsx into DataFrames
│   ├── tools/
│   │   ├── document_search.py   # ChromaDB-backed policy/contract search
│   │   ├── structured_data.py   # Account/order/ticket lookups + calculations
│   │   └── actions.py           # Mocked propose/confirm action store
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.jsx              # Login, chat UI, tool-trace, action-confirm cards
│       ├── DashboardPage.jsx    # SLA breach / recurring issue view
│       └── api.js               # Backend API client
├── data/                        # Source PDFs + xlsx
└── README.md
```