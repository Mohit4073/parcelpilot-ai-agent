import { useState, useEffect, useRef } from "react";
import { loginUser, listUsers, sendChatMessage, confirmAction } from "./api";
import "./App.css";
import DashboardPage from "./DashboardPage";
// One session id per browser tab load. Matches the backend's in-memory
// session_id -> chat object model.
const SESSION_ID = crypto.randomUUID();

export default function App() {
  const [users, setUsers] = useState([]);
  const [currentUser, setCurrentUser] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [confirmingId, setConfirmingId] = useState(null);
  const bottomRef = useRef(null);
  const [view, setView] = useState("chat");

  useEffect(() => {
    listUsers().then(setUsers).catch(console.error);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleLogin(userId) {
    const user = await loginUser(SESSION_ID, userId);
    setCurrentUser(user);
    setMessages([]);
  }

  async function handleSend() {
    if (!input.trim() || loading) return;
    const userMessage = input.trim();
    setInput("");
    setMessages((m) => [...m, { role: "user", text: userMessage }]);
    setLoading(true);

    try {
      const result = await sendChatMessage(SESSION_ID, userMessage);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text: result.answer,
          toolTrace: result.tool_trace,
          pendingActions: result.pending_actions,
        },
      ]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text: `Error: ${e.message}`, isError: true }]);
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirm(actionId) {
    setConfirmingId(actionId);
    try {
      const result = await confirmAction(SESSION_ID, actionId);
      setMessages((m) =>
        m.map((msg) => ({
          ...msg,
          pendingActions: msg.pendingActions?.map((a) =>
            a.action_id === actionId ? { ...a, status: result.status } : a
          ),
        }))
      );
    } catch (e) {
      alert(`Could not confirm action: ${e.message}`);
    } finally {
      setConfirmingId(null);
    }
  }

  if (!currentUser) {
    return (
      <div className="login-screen">
        <h1>ParcelPilot Internal Assistant</h1>
        <p>Select a user to log in as:</p>
        <div className="user-list">
          {users.map((u) => (
            <button key={u.user_id} className="user-button" onClick={() => handleLogin(u.user_id)}>
              <strong>{u.name}</strong>
              <span className="role-tag">{u.role.replace("_", " ")}</span>
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="chat-screen">
      <header className="chat-header">
        <div>
          <strong>{currentUser.name}</strong>
          <span className="role-tag">{currentUser.role.replace("_", " ")}</span>
        </div>
        <div className="tabs">
          <button className={view === "chat" ? "tab active" : "tab"} onClick={() => setView("chat")}>Chat</button>
          <button className={view === "dashboard" ? "tab active" : "tab"} onClick={() => setView("dashboard")}>Dashboard</button>
        </div>
        <button className="logout-button" onClick={() => setCurrentUser(null)}>
          Switch user
        </button>
      </header>

      {view === "dashboard" ? (
        <DashboardPage sessionId={SESSION_ID} />
      ) : (
        <>
          <div className="message-list">
            {messages.length === 0 && (
              <div className="empty-state">
                Ask about an order, ticket, cancellation fee, service credit, or policy question.
              </div>
            )}
            {messages.map((msg, i) => (
              <div key={i} className={`message ${msg.role} ${msg.isError ? "error" : ""}`}>
                {/* ... all your existing message rendering code stays exactly as it was ... */}
              </div>
            ))}
            {loading && <div className="message assistant"><div className="typing">Thinking...</div></div>}
            <div ref={bottomRef} />
          </div>

          <div className="input-bar">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              placeholder="Ask a question..."
              disabled={loading}
            />
            <button onClick={handleSend} disabled={loading}>Send</button>
          </div>
        </>
      )}
    </div>
  );
}