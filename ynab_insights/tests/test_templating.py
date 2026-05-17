"""Unit tests for the `dollars` Jinja filter."""

from app.templating import dollars


def test_dollars_formats_positive_cents() -> None:
    assert dollars(15000) == "$150.00"


def test_dollars_formats_negative_cents_with_leading_sign() -> None:
    # Sign goes before the $ in conventional accounting format.
    assert dollars(-2838606) == "-$28,386.06"


def test_dollars_formats_zero() -> None:
    assert dollars(0) == "$0.00"


def test_dollars_groups_thousands() -> None:
    assert dollars(1234567) == "$12,345.67"


def test_dollars_handles_none() -> None:
    assert dollars(None) == "—"


def test_dollars_small_amounts() -> None:
    assert dollars(99) == "$0.99"
    assert dollars(-99) == "-$0.99"
