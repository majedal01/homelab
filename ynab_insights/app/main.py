"""FastAPI app entry point (v2.5).

No database, no scheduler, no migrations. State is in-memory sessions only.
"""

from fastapi import FastAPI

from app import insights as _insights  # noqa: F401  side-effect: registers generators
from app.config import get_settings
from app.logging_config import setup_logging
from app.routers import ask, health, insights, snapshot
from app.routers import metrics as metrics_router
from app.routers import session as session_router
from app.session import RateLimitMiddleware, SessionMiddleware, get_session_store
from app.session.proxy_headers import ProxyHeaderMiddleware

setup_logging(get_settings().app_env)

app = FastAPI(title="ynab-insights", version=get_settings().app_version)
# Middleware runs outermost-last. Order matters:
# - ProxyHeader runs FIRST (outermost) so its warning fires before anything
#   else mutates state.
# - RateLimit runs AFTER SessionMiddleware so it can bucket on the resolved
#   sid for authed requests.
app.add_middleware(RateLimitMiddleware, settings=get_settings())
app.add_middleware(SessionMiddleware, store=get_session_store())
app.add_middleware(
    ProxyHeaderMiddleware,
    require_proxy_headers=get_settings().require_proxy_headers,
)
app.include_router(health.router)
app.include_router(session_router.router)
app.include_router(insights.router)
app.include_router(snapshot.router)
app.include_router(ask.router)
app.include_router(metrics_router.router)
