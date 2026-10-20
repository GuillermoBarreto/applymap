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


def load_profile(path: str | Path | None = None) -> Dict[str, Any]:
    """Load a profile YAML file and return a normalized dict."""
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
    return normalize(data)


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

    profile = {
        "name": data.get("name", ""),
        "headline": data.get("headline", ""),
        # Coerce non-string skills (e.g. a bare `123` in YAML) to strings so
        # a hand-edited profile never crashes the matcher.
        "skills": [
            str(s).strip().lower()
            for s in _as_list(data.get("skills", []))
            if s and str(s).strip()
        ],
        "experience": [str(e) for e in _as_list(data.get("experience", []))],
        "target_roles": [str(r) for r in _as_list(data.get("target_roles", []))],
        "location": data.get("location", ""),
    }
    # De-duplicate skills while preserving order.
    profile["skills"] = list(dict.fromkeys(profile["skills"]))
    return profile


def skill_list(profile: Dict[str, Any]) -> List[str]:
    return list(profile.get("skills", []))
