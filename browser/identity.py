"""Deterministic identity for browser elements observed by Tara."""

import hashlib
from collections import defaultdict


def _element_fingerprint(element_type, element):
    """Return the historical Tara fingerprint without page-specific selectors."""
    attributes = [
        element_type,
        element.get_attribute("id"),
        element.get_attribute("name"),
        element.get_attribute("aria-label"),
        element.get_attribute("placeholder"),
        element.get_attribute("type"),
        element.get_attribute("href"),
        element.get_attribute("value"),
    ]

    try:
        text = element.inner_text().strip()
    except Exception:
        text = ""

    attributes.append(text)
    raw = "|".join(str(attribute or "") for attribute in attributes)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def stable_element_ids(element_type, elements):
    """Build deterministic IDs, disambiguating otherwise identical siblings.

    Unique elements retain Tara's existing ``type_<sha1>`` ID format. Only
    duplicate fingerprints receive a deterministic ordinal suffix.
    """
    bases = [f"{element_type}_{_element_fingerprint(element_type, element)}" for element in elements]
    totals = defaultdict(int)
    for base in bases:
        totals[base] += 1

    occurrences = defaultdict(int)
    results = []
    for base in bases:
        occurrences[base] += 1
        if totals[base] == 1:
            results.append(base)
        else:
            results.append(f"{base}_{occurrences[base]}")
    return results
