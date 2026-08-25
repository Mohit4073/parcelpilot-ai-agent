"""
Mocked auth/identity layer.
In a real system this would come from a session/JWT.
For this assessment, the frontend sends a role + user_id at login,
and the backend trusts it as the request's identity context.
"""

from dataclasses import dataclass
from typing import Literal

Role = Literal["support_agent", "manager"]

@dataclass
class UserContext:
    user_id: str
    name: str
    role: Role

# Mocked internal users for the login screen
MOCK_USERS = {
    "rohit": UserContext(user_id="rohit", name="Rohit Sharma", role="support_agent"),
    "maya": UserContext(user_id="maya", name="Maya Iyer", role="support_agent"),
    "priya": UserContext(user_id="priya", name="Priya Mehta", role="manager"),
}

def get_user(user_id: str) -> UserContext:
    if user_id not in MOCK_USERS:
        raise ValueError(f"Unknown user: {user_id}")
    return MOCK_USERS[user_id]

def can_approve_high_value_credit(user: UserContext) -> bool:
    """Only managers can approve credits above the SOP's ₹1,000 threshold."""
    return user.role == "manager"