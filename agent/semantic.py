"""Shared semantic-key utilities for task facts and current-page targets."""

import re


def normalize_semantic_key(value: str) -> str:
    """Normalize a short human-readable semantic label into a stable key."""
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
    return normalized.strip("_")


def semantic_keys_match(left: str, right: str) -> bool:
    """Match normalized semantic labels without interpreting arbitrary prose."""
    left_key = normalize_semantic_key(left)
    right_key = normalize_semantic_key(right)
    return bool(left_key and right_key and (left_key == right_key or left_key in right_key or right_key in left_key))
