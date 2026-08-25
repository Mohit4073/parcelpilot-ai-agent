"""
FastAPI backend: exposes the chat agent and action-confirmation flow to the frontend.

Session model: each browser session gets a session_id (frontend generates a UUID
on load and sends it on every request). The Gemini `chat` object for that session
is kept in memory, keyed by session_id. This is intentionally simple for this
assessment — a production version would persist history and rebuild the chat
object per-request instead.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from auth import get_user, MOCK_USERS, UserContext
from agent import run_agent, new_chat
from tools import actions
from dashboard import get_dashboard_data

app = FastAPI(title="ParcelPilot AI Agent")

# Allow the React dev server (and later, your deployed frontend) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://parcelpilot-ai-agent-ten.vercel.app/", "http://localhost:5173"],  # tighten this to your actual frontend URL before final submission
    allow_methods=["*"],
    allow_headers=["*"],
)

# session_id -> Gemini chat object (in-memory, resets on server restart)
_sessions: dict[str, object] = {}
# session_id -> UserContext (so we know who owns each session)
_session_users: dict[str, UserContext] = {}


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    session_id: str
    user_id: str  # 'rohit', 'maya', or 'priya' — see auth.py MOCK_USERS


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ConfirmActionRequest(BaseModel):
    session_id: str
    action_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/users")
def list_users():
    """Lets the frontend render a login/role picker without hardcoding names."""
    return [{"user_id": u.user_id, "name": u.name, "role": u.role} for u in MOCK_USERS.values()]


@app.post("/login")
def login(req: LoginRequest):
    try:
        user = get_user(req.user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Unknown user")

    _session_users[req.session_id] = user
    _sessions[req.session_id] = new_chat(user)
    return {"user_id": user.user_id, "name": user.name, "role": user.role}


def _get_session_user(session_id: str) -> UserContext:
    user = _session_users.get(session_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not logged in. Call /login first.")
    return user


@app.post("/chat")
def chat(req: ChatRequest):
    user = _get_session_user(req.session_id)
    chat_obj = _sessions.get(req.session_id)

    result = run_agent(req.message, user, chat=chat_obj)
    _sessions[req.session_id] = result["chat"]  # persist updated chat state

    return {
        "answer": result["answer"],
        "tool_trace": result["tool_trace"],
        "pending_actions": result["pending_actions"],
    }

@app.get("/dashboard")
def dashboard(session_id: str):
    user = _get_session_user(session_id)
    return get_dashboard_data(user)

@app.post("/confirm-action")
def confirm_action(req: ConfirmActionRequest):
    """
    The ONLY path by which a proposed action actually executes.
    The model can never call this itself — only a direct user click does.
    """
    user = _get_session_user(req.session_id)
    result = actions.confirm_action(req.action_id, user)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/health")
def health():
    return {"status": "ok"}