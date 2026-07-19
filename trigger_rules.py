"""Generic Home Assistant entity trigger rule evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MISSING = object()

OPERATORS = {
    "equals",
    "not_equals",
    "contains",
    "not_contains",
    "one_of",
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
    "exists",
    "not_exists",
    "changes",
    "changes_to",
}

OPERATORS_WITHOUT_VALUE = {"exists", "not_exists", "changes"}


def resolve_field(entity: object, field: str) -> object:
    """Resolve a dot-separated field from an entity dictionary."""
    current = entity
    for part in (field or "state").split("."):
        if not isinstance(current, Mapping) or part not in current:
            return MISSING
        current = current[part]
    return current


def rule_matches(
    operator: str,
    actual: object,
    expected: object = "",
    *,
    previous: object = MISSING,
    case_sensitive: bool = False,
) -> bool:
    """Return whether an actual entity value satisfies a trigger rule."""
    if operator == "exists":
        return actual is not MISSING
    if operator == "not_exists":
        return actual is MISSING
    if actual is MISSING:
        return False

    if operator == "changes":
        return previous is not MISSING and not _equal(actual, previous, case_sensitive)
    if operator == "changes_to":
        return (
            previous is not MISSING
            and not _equal(actual, previous, case_sensitive)
            and _equal(actual, expected, case_sensitive)
        )
    if operator == "equals":
        return _equal(actual, expected, case_sensitive)
    if operator == "not_equals":
        return not _equal(actual, expected, case_sensitive)

    actual_text = _text(actual, case_sensitive)
    expected_text = _text(expected, case_sensitive)
    if operator == "contains":
        return expected_text in actual_text
    if operator == "not_contains":
        return expected_text not in actual_text
    if operator == "one_of":
        choices = [_text(choice.strip(), case_sensitive) for choice in str(expected).split(",")]
        return actual_text in choices

    try:
        actual_number = float(actual)
        expected_number = float(expected)
    except (TypeError, ValueError):
        return False
    if operator == "greater_than":
        return actual_number > expected_number
    if operator == "greater_than_or_equal":
        return actual_number >= expected_number
    if operator == "less_than":
        return actual_number < expected_number
    if operator == "less_than_or_equal":
        return actual_number <= expected_number
    return False


def display_value(value: object) -> str:
    """Convert a rule value to a template-safe string."""
    return "" if value is MISSING or value is None else str(value)


def _equal(left: object, right: object, case_sensitive: bool) -> bool:
    return _text(left, case_sensitive) == _text(right, case_sensitive)


def _text(value: object, case_sensitive: bool) -> str:
    text = "" if value is None else str(value).strip()
    return text if case_sensitive else text.casefold()
