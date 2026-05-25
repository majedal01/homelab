"""Shared test setup for v2.5.

Sets env vars before any app modules import so the cached Settings picks
up test-friendly values. No SQLAlchemy fixtures; v2.5 has no database.

The rate-limit limits are bumped so the suite doesn't trip the per-IP
session-create bucket (default 5/hr) across the ~9 POST /api/session
calls a full router run makes.
"""

import os

os.environ.setdefault("APP_ENV", "stage")
os.environ.setdefault("APP_VERSION", "test")
os.environ.setdefault("SESSION_SECRET_KEY", "test-secret-do-not-use-in-prod")

# Disable rate-limit interference in tests. Production / stage keep the
# real numbers; tests run against `app.main:app` which reads these once
# at startup.
os.environ.setdefault("RATE_LIMIT_SESSION_CREATE_PER_HOUR", "10000")
os.environ.setdefault("RATE_LIMIT_SNAPSHOT_PER_HOUR", "10000")
os.environ.setdefault("RATE_LIMIT_GENERATE_PER_HOUR", "10000")
os.environ.setdefault("RATE_LIMIT_ASK_PER_HOUR", "10000")
os.environ.setdefault("RATE_LIMIT_READS_PER_MINUTE", "10000")
os.environ.setdefault("DEMO_SESSION_RATE_LIMIT_PER_IP_PER_HOUR", "10000")
