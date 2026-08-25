"""
Agent orchestrator: wires Gemini's native function calling to the three tools
(document_search, structured_data, actions), using the current google-genai SDK.
Tools are plain Python functions with type hints + docstrings — the SDK
generates the schema and executes them automatically (Automatic Function Calling).
"""

import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
import time
from google.genai import errors

from auth import UserContext
from tools import document_search, structured_data, actions

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

MODEL_NAME = "gemini-3.1-flash-lite"

SYSTEM_INSTRUCTION = """
You are an internal support assistant for ParcelPilot, a logistics company.
You help support agents answer questions about accounts, orders, tickets, and policy.

SOURCE PRECEDENCE (always follow this order when sources conflict):
1. A signed customer agreement/contract (only applies to that specific account)
2. Current support policy / SOP documents
3. Current product documentation
Historical ticket "resolutions" are NEVER authoritative — they may be wrong.
Never cite or rely on a deprecated document unless the user explicitly asks
for historical/old policy information.

SEVERITY DEFINITIONS (apply these to classify tickets, per Support Policy v3):
- P1 Critical: complete outage, confirmed security incident/credential exposure,
  or immediate material business risk with no workaround.
- P2 High: major feature degraded but workaround exists or core ops still possible.
- P3 Normal: minor defect, how-to question, or limited-impact issue.

RULES:
- Use search_documents for policy/contract/product questions.
- Use the structured-data functions for account/order/ticket facts and calculations
  (cancellation fees, service credits, SLA breach status). Do not calculate these
  yourself from raw dates — always call the calculation function.
- Never promise a service credit if carrier fault or timing is unknown/ambiguous.
- If an action should be taken (escalation, ticket update, credit approval), call
  propose_action. NEVER assume it is confirmed — the user must explicitly confirm
  in the UI before anything happens.
- If sources conflict, state the conflict explicitly and say which source wins
  and why, citing the document name.
- If a response-time target is already breached, say so clearly and recommend
  escalation rather than downplaying it.
- Be concise and cite the source document name for any policy-based claim.
"""


def build_tools(user: UserContext) -> list:
    """
    Builds per-request tool functions bound to the current user via closure.
    `user` is deliberately NOT a parameter the model can see/fill in — it's
    injected here so every tool call is scoped to whoever is logged in.
    """

    def search_documents(query: str, account_id: str = "", include_deprecated: bool = False) -> list[dict]:
        """Semantic search over ParcelPilot policy, SOP, product docs, and contracts.

        Args:
            query: What to search for.
            account_id: Account ID like ACCT-001 to scope to that account's own
                contract, or empty string if the question isn't account-specific.
            include_deprecated: True only if the user explicitly asked for old
                or historical policy information.
        """
        return document_search.search_documents(query, account_id or None, include_deprecated)

    def get_account(account_id: str) -> dict:
        """Look up account details: plan, CSM, contract file, premium support status.

        Args:
            account_id: e.g. ACCT-001
        """
        return structured_data.get_account(account_id, user)

    def get_order(order_id: str) -> dict:
        """Look up a single order's full details (status, timestamps, fault flags).

        Args:
            order_id: e.g. ORD-1001
        """
        return structured_data.get_order(order_id, user)

    def get_tickets(account_id: str = "", status: str = "") -> list[dict]:
        """List support tickets, optionally filtered.

        Args:
            account_id: Filter to this account, or empty string for all accounts.
            status: 'open' or 'closed', or empty string for all statuses.
        """
        return structured_data.get_tickets(user, account_id or None, status or None)

    def calc_cancellation_fee(order_id: str) -> dict:
        """Determine whether an order can be cancelled right now and what fee applies.

        Args:
            order_id: e.g. ORD-1001
        """
        return structured_data.calc_cancellation_fee(order_id, user)

    def calc_service_credit(order_id: str) -> dict:
        """Determine failed-pickup service-credit eligibility and amount for an order.

        Args:
            order_id: e.g. ORD-2002
        """
        return structured_data.calc_service_credit(order_id, user)

    def check_sla_status(ticket_id: str, severity: str) -> dict:
        """Check whether a ticket's first-response SLA target is breached.
        You must first classify severity yourself (P1/P2/P3) using Support
        Policy v3's severity definitions before calling this.

        Args:
            ticket_id: e.g. TKT-501
            severity: 'P1', 'P2', or 'P3'
        """
        return structured_data.check_sla_status(ticket_id, severity, user)

    def propose_action(action_type: str, reason: str, ticket_id: str = "",
                        order_id: str = "", credit_inr: float = 0) -> dict:
        """Draft an action for the user to review and confirm in the UI.
        This does NOT execute anything by itself — it only creates a pending draft.

        Args:
            action_type: 'create_escalation', 'update_ticket', or 'create_followup_task'
            reason: Why this action is being proposed.
            ticket_id: Related ticket ID, if any, else empty string.
            order_id: Related order ID, if any, else empty string.
            credit_inr: Credit amount in INR if applicable, else 0.
        """
        payload = {"reason": reason}
        if ticket_id:
            payload["ticket_id"] = ticket_id
        if order_id:
            payload["order_id"] = order_id
        if credit_inr:
            payload["credit_inr"] = credit_inr
        return actions.propose_action(action_type, payload, user)

    return [search_documents, get_account, get_order, get_tickets,
            calc_cancellation_fee, calc_service_credit, check_sla_status, propose_action]


def new_chat(user: UserContext):
    """Starts a fresh chat session for this user, with tools bound to them."""
    return client.chats.create(
        model=MODEL_NAME,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=build_tools(user),
        ),
    )


def run_agent(user_message: str, user: UserContext, chat=None) -> dict:
    """
    Runs one turn. Pass back the returned `chat` object on the next call to
    continue the same conversation (keeps tool context + history).
    Retries once after a short pause if we hit the free-tier rate limit.
    """
    if chat is None:
        chat = new_chat(user)

    history_len_before = len(chat.get_history())

    try:
        response = chat.send_message(user_message)
    except errors.ClientError as e:
        if "RESOURCE_EXHAUSTED" in str(e) or "quota" in str(e).lower():
            time.sleep(20)
            try:
                response = chat.send_message(user_message)
            except errors.ClientError:
                time.sleep(30)
                response = chat.send_message(user_message)
        else:
            raise

    # Only inspect content added THIS turn — chat.get_history() returns the
    # whole conversation, and re-scanning old turns would re-surface earlier
    # tool calls/actions (e.g. an old escalation) on every later message.
    full_history = chat.get_history()
    new_content = full_history[history_len_before:]

    tool_trace = []
    pending_actions = []
    for content in new_content:
        for part in content.parts:
            if part.function_call:
                tool_trace.append({"tool": part.function_call.name, "args": dict(part.function_call.args)})
            if part.function_response:
                fr = part.function_response
                raw = fr.response
                result = raw.get("result", raw) if isinstance(raw, dict) else raw
                if fr.name == "propose_action" and isinstance(result, dict) and "action_id" in result:
                    pending_actions.append(result)

    return {
        "answer": response.text,
        "tool_trace": tool_trace,
        "pending_actions": pending_actions,
        "chat": chat,
    }

if __name__ == "__main__":
    from auth import get_user
    u = get_user("rohit")

    result = run_agent("Can Northstar cancel ORD-1001 without a cancellation fee?", u)
    print("ANSWER:\n", result["answer"])
    print("\nTOOL TRACE:")
    for t in result["tool_trace"]:
        print(" -", t)