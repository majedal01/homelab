"""Session layer: per-user in-memory state with TTL eviction.

Tokens, the YNAB snapshot, and generated insights all live here. Nothing in
this package writes to disk; restart clears every session.
"""

from app.session.middleware import SessionMiddleware, current_session
from app.session.models import UserSession
from app.session.rate_limit import RateLimitMiddleware
from app.session.store import SessionStore, get_session_store

__all__ = [
    "RateLimitMiddleware",
    "SessionMiddleware",
    "SessionStore",
    "UserSession",
    "current_session",
    "get_session_store",
]
