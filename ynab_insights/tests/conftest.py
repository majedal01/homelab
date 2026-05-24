"""Shared test setup for v2.5.

Sets env vars before any app modules import so the cached Settings picks
up test-friendly values. No SQLAlchemy fixtures; v2.5 has no database.
"""

import os

os.environ.setdefault("APP_ENV", "stage")
os.environ.setdefault("APP_VERSION", "test")
os.environ.setdefault("SESSION_SECRET_KEY", "test-secret-do-not-use-in-prod")
