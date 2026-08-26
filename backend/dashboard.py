"""
Problem 1: Proactive issue detection.
Rule-based (not ML) on purpose — deterministic, explainable, and testable
against the known dataset, per the design plan.
"""

from tools.structured_data import tickets_df, accounts_df, check_sla_status, DATASET_SNAPSHOT
from auth import UserContext

# Keyword -> known issue mapping, used to flag tickets that likely match a
# documented bug rather than being a brand-new incident.
KNOWN_ISSUE_KEYWORDS = {
    "KI-208": ["bulk upload", "csv", "upload fail"],
    "KI-211": ["still shows booked", "webhook", "pickup", "not picked up"],
}

# Naive severity classifier from ticket subject/description text, mirroring
# the same P1/P2/P3 definitions the agent uses (Support Policy v3 Section 2).
def _classify_severity(ticket: dict) -> str:
    """
    Mirrors Support Policy v3 Section 2's severity definitions as keyword
    signals. P1 checked first and matched broadly, since under-classifying
    a true outage/security incident is the worse failure mode.
    """
    text = f"{ticket.get('subject', '')} {ticket.get('description', '')}".lower()

    p1_signals = [
        "outage", "security", "credential", "api key", "exposed", "breach",
        "all shipment", "every user", "cannot create", "unable to create",
        "http 500", "500 error", "down for all",
    ]
    if any(s in text for s in p1_signals):
        return "P1"

    p2_signals = [
        "degraded", "not working", "delay", "some users", "intermittent",
        "webhook", "bulk upload", "upload fail",
    ]
    if any(s in text for s in p2_signals):
        return "P2"

    return "P3"


def get_dashboard_data(user: UserContext) -> dict:
    open_tickets = tickets_df[tickets_df["status"] == "open"]

    sla_alerts = []
    known_issue_matches = []

    for _, row in open_tickets.iterrows():
        ticket = row.to_dict()
        severity = _classify_severity(ticket)

        sla = check_sla_status(ticket["ticket_id"], severity, user)
        if "error" not in sla:
            sla_alerts.append({
                "ticket_id": ticket["ticket_id"],
                "account_id": ticket["account_id"],
                "severity": severity,
                "elapsed_hours": sla["elapsed_hours"],
                "target_hours": sla["target_hours"],
                "breached": sla["breached"],
                "source": sla["source"],
            })

        text = f"{ticket.get('subject', '')} {ticket.get('description', '')}".lower()
        for ki_id, keywords in KNOWN_ISSUE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                known_issue_matches.append({
                    "ticket_id": ticket["ticket_id"],
                    "account_id": ticket["account_id"],
                    "matched_issue": ki_id,
                })

    # Recurring pattern: same known issue hit by >=2 distinct tickets (open or closed)
    all_tickets = tickets_df.to_dict("records")
    issue_counts: dict[str, set] = {}
    for t in all_tickets:
        text = f"{t.get('subject', '')} {t.get('description', '')}".lower()
        for ki_id, keywords in KNOWN_ISSUE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                issue_counts.setdefault(ki_id, set()).add(t["ticket_id"])

    recurring_clusters = [
        {"issue": ki_id, "ticket_count": len(ids), "ticket_ids": sorted(ids)}
        for ki_id, ids in issue_counts.items() if len(ids) >= 2
    ]

    breached = [a for a in sla_alerts if a["breached"]]
    near_breach = [a for a in sla_alerts if not a["breached"] and a["elapsed_hours"] >= 0.7 * a["target_hours"]]

    return {
        "snapshot_time": DATASET_SNAPSHOT.isoformat(),
        "sla_breached": sorted(breached, key=lambda a: -a["elapsed_hours"]),
        "sla_near_breach": near_breach,
        "known_issue_matches": known_issue_matches,
        "recurring_clusters": recurring_clusters,
    }