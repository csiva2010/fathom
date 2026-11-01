"""Importing this package registers every table on Base.metadata (used by Alembic)."""

from src.data.db.models.api_token import ApiToken
from src.data.db.models.conversation import Conversation, Feedback
from src.data.db.models.goal import Goal
from src.data.db.models.portfolio import Holding, Portfolio
from src.data.db.models.profile import Profile
from src.data.db.models.user import User

__all__ = [
    "ApiToken",
    "Conversation",
    "Feedback",
    "Goal",
    "Holding",
    "Portfolio",
    "Profile",
    "User",
]
