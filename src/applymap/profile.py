"""Load the user's profile: skills, background, and target roles.

The profile lives outside the repo (default: ~/.applymap/profile.yaml) so
personal details are never committed. See examples/profile.example.yaml.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import yaml

DEFAULT_PROFILE_PATH = Path(os.environ.get("APPLYMAP_PROFILE", "~/.applymap/profile.yaml")).expanduser()

# Fields normalize() knows. Anything else in the YAML is silently
# ignored — usually a typo, which check-profile now flags.
KNOWN_FIELDS = {"name", "headline", "location", "target_roles", "skills", "experience"}


def unknown_fields(data: Dict[str, Any]) -> List[str]:
    """Top-level keys normalize() doesn't know, sorted for stable output."""
    return sorted(set(data) - KNOWN_FIELDS)


def _read_profile_yaml(path: str | Path | None = None) -> Dict[str, Any]:
    """Read the profile YAML mapping without normalizing it."""
    resolved = Path(path).expanduser() if path else DEFAULT_PROFILE_PATH
    if not resolved.exists():
        raise FileNotFoundError(
            f"Profile not found at {resolved}. Run `applymap init-profile` to create one, "
            "or set APPLYMAP_PROFILE to its location."
        )
    try:
        with open(resolved, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        raise RuntimeError(
            f"Profile at {resolved} is not valid YAML: {exc}. "
            "Fix the syntax (quoting, indentation, brackets), then try again."
        ) from exc
    if not isinstance(data, dict):
        raise RuntimeError(
            f"Profile at {resolved} must be a YAML mapping of profile fields, "
            f"but contains {type(data).__name__}."
        )
    return data


def load_raw_profile(path: str | Path | None = None) -> Dict[str, Any]:
    """Load the profile YAML mapping without normalizing (for typo checks)."""
    return _read_profile_yaml(path)


def load_profile(path: str | Path | None = None) -> Dict[str, Any]:
    """Load a profile YAML file and return a normalized dict."""
    return normalize(_read_profile_yaml(path))


def normalize(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize raw profile data into the fields applymap expects."""
    def _as_list(value):
        if value is None:
            # A bare `experience:` (or `skills:`) key in hand-edited YAML is
            # None, not an empty list — treat it as empty instead of
            # producing ["None"].
            return []
        # A hand-edited profile might use a bare `skills: python` instead of
        # a YAML list; wrap it so we never iterate over a string's characters.
        return value if isinstance(value, list) else [value]

    def _as_text(value):
        # The scalar fields used to pass through raw: a bare `name:` in
        # hand-edited YAML is None, and the cover letter opened with
        # "Candidate: None — ...". Coerce like the list fields do.
        return "" if value is None else str(value).strip()

    profile = {
        "name": _as_text(data.get("name", "")),
        "headline": _as_text(data.get("headline", "")),
        # Coerce non-string skills (e.g. a bare `123` in YAML) to strings so
        # a hand-edited profile never crashes the matcher.
        "skills": [
            str(s).strip().lower()
            for s in _as_list(data.get("skills", []))
            if s and str(s).strip()
        ],
        # Skills already filtered nulls; experience and target roles did
        # not, so a bare `experience: [null]` in hand-edited YAML leaked
        # the literal string "None" into cover letters and reports.
        "experience": [str(e).strip() for e in _as_list(data.get("experience", []))
                       if e is not None and str(e).strip()],
        "target_roles": [str(r).strip() for r in _as_list(data.get("target_roles", []))
                         if r is not None and str(r).strip()],
        "location": _as_text(data.get("location", "")),
    }
    # De-duplicate skills while preserving order.
    profile["skills"] = list(dict.fromkeys(profile["skills"]))
    # Experience and target roles get the same treatment: a repeated line
    # in a hand-edited profile used to repeat in cover letters and reports.
    profile["experience"] = list(dict.fromkeys(profile["experience"]))
    profile["target_roles"] = list(dict.fromkeys(profile["target_roles"]))
    return profile


def skill_list(profile: Dict[str, Any]) -> List[str]:
    return list(profile.get("skills", []))
