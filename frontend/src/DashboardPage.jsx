import { useState, useEffect } from "react";
import { getDashboard } from "./api";

export default function DashboardPage({ sessionId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getDashboard(sessionId).then(setData).catch((e) => setError(e.message));
  }, [sessionId]);

  if (error) return <div className="dashboard-error">Error: {error}</div>;
  if (!data) return <div className="dashboard-loading">Loading...</div>;

  return (
    <div className="dashboard">
      <div className="dashboard-section">
        <h3>🚨 SLA Breached ({data.sla_breached.length})</h3>
        {data.sla_breached.length === 0 && <p className="dim">None</p>}
        {data.sla_breached.map((a) => (
          <div key={a.ticket_id} className="alert-card breach">
            <strong>{a.ticket_id}</strong> ({a.account_id}) — {a.severity}
            <div className="dim">
              {a.elapsed_hours}h elapsed / {a.target_hours}h target — {a.source}
            </div>
          </div>
        ))}
      </div>

      <div className="dashboard-section">
        <h3>⏰ Near SLA Breach ({data.sla_near_breach.length})</h3>
        {data.sla_near_breach.length === 0 && <p className="dim">None</p>}
        {data.sla_near_breach.map((a) => (
          <div key={a.ticket_id} className="alert-card warn">
            <strong>{a.ticket_id}</strong> ({a.account_id}) — {a.severity}
            <div className="dim">{a.elapsed_hours}h elapsed / {a.target_hours}h target</div>
          </div>
        ))}
      </div>

      <div className="dashboard-section">
        <h3>🔁 Recurring Known Issues ({data.recurring_clusters.length})</h3>
        {data.recurring_clusters.length === 0 && <p className="dim">None</p>}
        {data.recurring_clusters.map((c) => (
          <div key={c.issue} className="alert-card cluster">
            <strong>{c.issue}</strong> — {c.ticket_count} tickets: {c.ticket_ids.join(", ")}
          </div>
        ))}
      </div>
    </div>
  );
}