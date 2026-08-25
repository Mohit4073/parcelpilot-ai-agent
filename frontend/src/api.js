const API_BASE = "https://parcelpilot-ai-agent-5dkg.onrender.com";

export async function loginUser(sessionId, userId) {
  const res = await fetch(`${API_BASE}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, user_id: userId }),
  });
  if (!res.ok) throw new Error("Login failed");
  return res.json();
}

export async function listUsers() {
  const res = await fetch(`${API_BASE}/users`);
  if (!res.ok) throw new Error("Failed to fetch users");
  return res.json();
}

export async function sendChatMessage(sessionId, message) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  if (!res.ok) throw new Error("Chat request failed");
  return res.json();
}

export async function confirmAction(sessionId, actionId) {
  const res = await fetch(`${API_BASE}/confirm-action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, action_id: actionId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Confirm failed");
  }
  return res.json();
}

export async function getDashboard(sessionId) {
  const res = await fetch(`${API_BASE}/dashboard?session_id=${sessionId}`);
  if (!res.ok) throw new Error("Dashboard request failed");
  return res.json();
}