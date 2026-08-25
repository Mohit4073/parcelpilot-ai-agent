"""
Structured data tool: typed, scoped lookup + calculation functions
over the accounts/orders/tickets DataFrames.

Design rule: the LLM never gets raw DataFrame/SQL access. It can only call
these specific functions, each of which enforces its own account/role scoping.
This is where cancellation-fee and service-credit business logic lives,
encoding the rules from SOP v4, overridden per-account where a contract says so.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from typing import Optional

import pandas as pd

from data_loader import load_structured_data, DATASET_SNAPSHOT
from auth import UserContext

_data = load_structured_data()
accounts_df = _data["accounts"]
orders_df = _data["orders"]
tickets_df = _data["tickets"]

def _clean(d: dict) -> dict:
    """Converts pandas NaN/NaT/Timestamp values into JSON-safe types."""
    cleaned = {}
    for k, v in d.items():
        if pd.isna(v):
            cleaned[k] = None
        elif isinstance(v, pd.Timestamp):
            cleaned[k] = v.isoformat()
        else:
            cleaned[k] = v
    return cleaned

# ---------------------------------------------------------------------------
# Account-level access check (used by every function below)
# ---------------------------------------------------------------------------

def _account_row(account_id: str) -> Optional[pd.Series]:
    rows = accounts_df[accounts_df["account_id"] == account_id]
    return rows.iloc[0] if not rows.empty else None


# ---------------------------------------------------------------------------
# Basic lookups
# ---------------------------------------------------------------------------

def get_account(account_id: str, user: UserContext) -> dict:
    row = _account_row(account_id)
    if row is None:
        return {"error": f"No account found with id {account_id}"}
    return _clean(row.to_dict())


def get_order(order_id: str, user: UserContext) -> dict:
    rows = orders_df[orders_df["order_id"] == order_id]
    if rows.empty:
        return {"error": f"No order found with id {order_id}"}
    return _clean(rows.iloc[0].to_dict())


def get_tickets(user: UserContext, account_id: Optional[str] = None,
                 status: Optional[str] = None) -> list[dict]:
    df = tickets_df.copy()
    if account_id:
        df = df[df["account_id"] == account_id]
    if status:
        df = df[df["status"] == status]

    return [_clean(row.to_dict()) for _, row in df.iterrows()]


# ---------------------------------------------------------------------------
# Business logic: cancellation fee
# ---------------------------------------------------------------------------

def calc_cancellation_fee(order_id: str, user: UserContext) -> dict:
    """
    Applies Cancellation & Service Credit SOP v4 Section 1, overridden by
    contract terms where applicable:
      - Northstar (ACCT-001): BOOKED, pre-pickup cancellations are always free
        per their enterprise agreement, regardless of elapsed time.
      - LumenWorks (ACCT-002): agreement explicitly defers to the standard SOP
        (no special cancellation-fee waiver) -> SOP applies as normal.
      - All other accounts: standard SOP applies.
    """
    order = get_order(order_id, user)
    if "error" in order:
        return order

    account_id = order["account_id"]
    status = order["status"]

    if status == "PICKED_UP":
        return {
            "order_id": order_id,
            "outcome": "cannot_cancel",
            "reason": "Order already PICKED_UP. Use return-to-origin workflow instead (SOP v4 Section 1).",
        }
    if status == "DELIVERED":
        return {
            "order_id": order_id,
            "outcome": "cannot_cancel",
            "reason": "Order already DELIVERED. Cannot be cancelled (SOP v4 Section 1).",
        }
    if status == "DRAFT":
        return {
            "order_id": order_id,
            "outcome": "cancel_free",
            "fee_inr": 0,
            "reason": "DRAFT orders may be cancelled with no fee (SOP v4 Section 1).",
        }

    # status == "BOOKED"
    if account_id == "ACCT-001":  # Northstar
        return {
            "order_id": order_id,
            "outcome": "cancel_free",
            "fee_inr": 0,
            "reason": (
                "Northstar Enterprise Agreement Section 2: BOOKED shipments may be "
                "cancelled pre-pickup with no fee, regardless of elapsed time. "
                "This overrides the standard SOP's 30-minute free window."
            ),
        }

    booked_at = pd.to_datetime(order["booked_at"])
    cancel_requested_at = pd.to_datetime(order.get("cancellation_requested_at")) \
        if order.get("cancellation_requested_at") else DATASET_SNAPSHOT

    minutes_since_booking = (cancel_requested_at - booked_at).total_seconds() / 60

    if minutes_since_booking <= 30:
        return {
            "order_id": order_id,
            "outcome": "cancel_free",
            "fee_inr": 0,
            "minutes_since_booking": round(minutes_since_booking, 1),
            "reason": "Within 30-minute free cancellation window (SOP v4 Section 1).",
        }
    else:
        return {
            "order_id": order_id,
            "outcome": "cancel_with_fee",
            "fee_inr": 250,
            "minutes_since_booking": round(minutes_since_booking, 1),
            "reason": (
                "Past the 30-minute free window, no contract waiver applies for this "
                "account -> INR 250 fee applies (SOP v4 Section 1)."
            ),
        }


# ---------------------------------------------------------------------------
# Business logic: failed-pickup service credit
# ---------------------------------------------------------------------------

def calc_service_credit(order_id: str, user: UserContext) -> dict:
    """
    Applies SOP v4 Section 2, overridden per-contract:
      - LumenWorks (ACCT-002): 4-hour threshold, flat INR 300 credit (contract
        explicitly replaces the default threshold/amount).
      - Northstar (ACCT-001): no override on threshold, but monthly credits
        capped at INR 5,000 aggregate per their agreement.
      - Default SOP: 2-hour threshold, credit = min(INR 500, 10% of shipment fee).
    Never promises a credit if fault/timing data is missing or ambiguous
    (per SOP v4 Section 3's explicit instruction).
    """
    order = get_order(order_id, user)
    if "error" in order:
        return order

    if order.get("carrier_fault") is not True:
        return {
            "order_id": order_id,
            "outcome": "not_eligible",
            "reason": "Carrier fault is not confirmed True. Do not promise a credit "
                      "when fault is unknown or not carrier-caused (SOP v4 Section 3).",
        }
    if order.get("customer_fault") is True:
        return {
            "order_id": order_id,
            "outcome": "not_eligible",
            "reason": "Customer-caused issue recorded; not eligible per SOP v4 Section 2.",
        }
    if not order.get("pickup_window_end"):
        return {
            "order_id": order_id,
            "outcome": "unknown",
            "reason": "Missing pickup_window_end data; cannot calculate delay.",
        }

    window_end = pd.to_datetime(order["pickup_window_end"])
    pickup_actual_raw = order.get("pickup_actual_at")
    pickup_actual = pd.to_datetime(pickup_actual_raw) if pickup_actual_raw else None
    reference_time = pickup_actual if pickup_actual is not None else DATASET_SNAPSHOT
    hours_late = (reference_time - window_end).total_seconds() / 3600
    account_id = order["account_id"]

    if account_id == "ACCT-002":  # LumenWorks
        threshold_hours, credit = 4, 300
        clause = "LumenWorks Service Agreement Section 3 (overrides default SOP threshold/amount)"
    else:
        threshold_hours = 2
        fee = order.get("shipment_fee_inr", 0) or 0
        credit = min(500, round(fee * 0.10, 2))
        clause = "SOP v4 Section 2 default"

    if hours_late < threshold_hours:
        return {
            "order_id": order_id,
            "outcome": "not_yet_eligible",
            "hours_late": round(hours_late, 2),
            "threshold_hours": threshold_hours,
            "reason": f"Only {round(hours_late, 2)}h past window end; threshold is {threshold_hours}h ({clause}).",
        }

    result = {
        "order_id": order_id,
        "outcome": "eligible",
        "hours_late": round(hours_late, 2),
        "credit_inr": credit,
        "reason": f"Past {threshold_hours}h threshold, carrier at fault -> credit per {clause}.",
    }
    if credit > 1000:
        result["requires_manager_approval"] = True
        result["reason"] += " NOTE: exceeds INR 1,000, requires manager approval (SOP v4 Section 3)."
    return result


# ---------------------------------------------------------------------------
# Business logic: SLA / first-response status
# ---------------------------------------------------------------------------

SUPPORT_POLICY_V3_TARGETS_HOURS = {
    # plan -> {severity: hours}, from Support Policy v3 Section 3
    "Enterprise": {"P1": 0.5, "P2": 2, "P3": 24},   # P1=30min, P3=1 business day (~24h simplified)
    "Growth":     {"P1": 2,   "P2": 4, "P3": 48},
    "Standard":   {"P1": 4,   "P2": 24, "P3": 48},
}

NORTHSTAR_TARGETS_HOURS = {"P1": 0.25, "P2": 1, "P3": 8}  # 15min / 1hr / 8 business hrs


def check_sla_status(ticket_id: str, severity: str, user: UserContext) -> dict:
    """
    severity must be passed in as 'P1' / 'P2' / 'P3' — determined by the caller
    (agent) applying Support Policy v3 Section 2 severity definitions to the
    ticket description, since severity isn't a column in the raw data.
    """
    rows = tickets_df[tickets_df["ticket_id"] == ticket_id]
    if rows.empty:
        return {"error": f"No ticket found with id {ticket_id}"}
    ticket = rows.iloc[0]
    account = _account_row(ticket["account_id"])
    plan = account["plan"] if account is not None else "Standard"
    account_id = ticket["account_id"]

    if account_id == "ACCT-001":  # Northstar contract override
        target_hours = NORTHSTAR_TARGETS_HOURS.get(severity)
        source = "Northstar Enterprise Agreement Section 1 (overrides standard policy)"
    else:
        target_hours = SUPPORT_POLICY_V3_TARGETS_HOURS.get(plan, {}).get(severity)
        source = f"Support Policy v3 Section 3 ({plan} plan)"

    if target_hours is None:
        return {"error": f"Could not determine SLA target for plan={plan}, severity={severity}"}

    created_at = ticket["created_at"]
    elapsed_hours = (DATASET_SNAPSHOT - created_at).total_seconds() / 3600
    breached = elapsed_hours > target_hours

    return {
        "ticket_id": ticket_id,
        "severity": severity,
        "plan": plan,
        "target_hours": target_hours,
        "elapsed_hours": round(elapsed_hours, 2),
        "breached": breached,
        "source": source,
    }


if __name__ == "__main__":
    from auth import get_user
    u = get_user("rohit")

    print("-- ORD-1001 (Northstar, BOOKED, cancel requested) --")
    print(calc_cancellation_fee("ORD-1001", u))

    print("\n-- ORD-2001 (LumenWorks, cancel 75min after booking) --")
    print(calc_cancellation_fee("ORD-2001", u))

    print("\n-- ORD-2002 (LumenWorks, carrier fault, still not picked up) --")
    print(calc_service_credit("ORD-2002", u))

    print("\n-- TKT-501 (Northstar, P1 outage) --")
    print(check_sla_status("TKT-501", "P1", u))

    print("\n-- TKT-504 (Northstar, P2-ish webhook confusion) --")
    print(check_sla_status("TKT-504", "P2", u))