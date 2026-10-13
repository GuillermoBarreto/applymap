"""Optional LLM layer over an OpenAI-compatible API.

Enabled only when APPLYMAP_API_KEY is set. All usage is explicit:
the user runs a command and the request goes out; nothing runs in the
background. No keys are ever stored — the env var is read at call time.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


def _config() -> Optional[Dict[str, str]]:
    api_key = os.environ.get("APPLYMAP_API_KEY", "")
    if not api_key:
        return None
    return {
        "api_key": api_key,
        "base_url": os.environ.get("APPLYMAP_API_BASE", "https://api.openai.com/v1").rstrip("/"),
        "model": os.environ.get("APPLYMAP_MODEL", "gpt-4o-mini"),
    }


def is_configured() -> bool:
    """True when an API key is available."""
    return _config() is not None


def chat(system: str, user: str, *, max_tokens: int = 800) -> str:
    """Send one chat-completion request and return the assistant text."""
    cfg = _config()
    if cfg is None:
        raise RuntimeError(
            "APPLYMAP_API_KEY is not set. Export it to enable AI features."
        )
    payload = {
        "model": cfg["model"],
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    req = urllib.request.Request(
        f"{cfg['base_url']}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"API request failed with HTTP {exc.code} "
            f"({exc.reason}). Check APPLYMAP_API_KEY, APPLYMAP_API_BASE, "
            "and your network connection."
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"API request failed: {exc.reason}. Check APPLYMAP_API_BASE "
            "and your network connection."
        ) from exc
    try:
        return body["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected API response shape: {body!r}") from exc


def draft_cover_letter(profile: Dict[str, Any], posting: str, company: str, role: str) -> str:
    """Draft a tailored cover letter. Never invents experience: it only
    works from the profile facts and flags gaps instead of fabricating."""
    skills = ", ".join(profile.get("skills", []))
    experience = "\n".join(f"- {e}" for e in profile.get("experience", []))
    system = (
        "You write honest, concise cover letters. Rules you must follow:\n"
        "1. Only describe experience and skills present in the candidate's profile.\n"
        "2. Never invent companies, metrics, job titles, or projects.\n"
        "3. If the posting asks for something the profile lacks, say the "
        "candidate is 'eager to grow in' it instead of claiming it.\n"
        "4. Keep it under 200 words. First person."
    )
    user = (
        f"Candidate: {profile.get('name', '')} — {profile.get('headline', '')}\n"
        f"Skills: {skills}\n"
        f"Experience:\n{experience}\n\n"
        f"Job posting for {role} at {company}:\n{posting[:4000]}"
    )
    return chat(system, user)


def summarize_gaps(profile: Dict[str, Any], missing: list) -> str:
    """Explain the missing skills in plain language and suggest next steps."""
    system = (
        "You are a pragmatic career coach. Given a candidate's skills and the "
        "skills missing from a job posting, write 3-5 short, concrete study "
        "suggestions. Be specific (docs, tutorials, projects), not motivational."
    )
    user = (
        f"Candidate skills: {', '.join(profile.get('skills', []))}\n"
        f"Missing for this role: {', '.join(missing)}"
    )
    return chat(system, user)
