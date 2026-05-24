"""FastAPI app entry point (v2.5).

No database, no scheduler, no migrations. State is in-memory sessions only.
"""

from fastapi import FastAPI

from app import insights as _insights  # noqa: F401  side-effect: registers generators
from app.config import get_settings
from app.logging_config import setup_logging
from app.routers import ask, health, insights
from app.routers import session as session_router
from app.session import RateLimitMiddleware, SessionMiddleware, get_session_store

setup_logging(get_settings().app_env)

app = FastAPI(title="ynab-insights", version=get_settings().app_version)
# Middleware runs outermost-last, so add RateLimit AFTER SessionMiddleware
# to ensure the session is resolved before rate limits bucket on it.
app.add_middleware(RateLimitMiddleware, settings=get_settings())
app.add_middleware(SessionMiddleware, store=get_session_store())
app.include_router(health.router)
app.include_router(session_router.router)
app.include_router(insights.router)
app.include_router(ask.router)
