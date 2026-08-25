"""
Mocked action tool: two-phase propose/confirm flow.
The agent (LLM) may only call propose_action. It can NEVER call confirm_action
directly — that only happens when the frontend sends an explicit user confirmation
back to the backend. This file just manages the in-memory store; main.py enforces
the two-phase rule at the API layer.
"""

import uuid
from datetime import datetime
from typing import Literal

from auth import UserContext, can_approve_high_value_credit

ActionType = Literal["create_escalation", "update_ticket", "create_followup_task"]

# In-memory store — resets on server restart, which is fine for a mocked tool.
_pending_actions: dict[str, dict] = {}
_confirmed_actions: list[dict] = []


def propose_action(action_type: ActionType, payload: dict, user: UserContext) -> dict:
    """
    Called by the agent to DRAFT an action. Does not execute anything.
    Returns a draft the frontend renders as a confirm/cancel card.
    """
    action_id = str(uuid.uuid4())[:8]

    # Gate: high-value credit actions need a manager, flagged here so the
    # frontend can show "needs manager approval" instead of a plain confirm.
    needs_manager = False
    if action_type == "update_ticket" and payload.get("credit_inr", 0) > 1000:
        needs_manager = not can_approve_high_value_credit(user)

    draft = {
        "action_id": action_id,
        "action_type": action_type,
        "payload": payload,
        "proposed_by": user.user_id,
        "proposed_at": datetime.utcnow().isoformat(),
        "status": "pending_confirmation",
        "needs_manager_approval": needs_manager,
    }
    _pending_actions[action_id] = draft
    return draft


def confirm_action(action_id: str, user: UserContext) -> dict:
    """
    Only called by the API layer in direct response to explicit user confirmation
    click — never by the agent/model itself.
    """
    draft = _pending_actions.get(action_id)
    if draft is None:
        return {"error": f"No pending action with id {action_id}"}

    if draft["needs_manager_approval"] and not can_approve_high_value_credit(user):
        return {"error": "This action requires manager approval and cannot be confirmed by this user."}

    draft["status"] = "confirmed"
    draft["confirmed_by"] = user.user_id
    draft["confirmed_at"] = datetime.utcnow().isoformat()
    _confirmed_actions.append(draft)
    del _pending_actions[action_id]
    return draft


def get_pending_action(action_id: str) -> dict | None:
    return _pending_actions.get(action_id)