"""Shared Jinja2 templates configuration. Lives outside any single router so
custom filters are registered exactly once at import time."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

_templates_dir = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


def dollars(cents: int | None) -> str:
    """Format integer cents as a USD-style string with the sign in the
    conventional position: `-$1,234.56` (not `$-1,234.56`)."""
    if cents is None:
        return "—"
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


templates.env.filters["dollars"] = dollars
