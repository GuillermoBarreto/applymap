"""Deterministic skill matching between a job posting and a user profile.

No API calls here: this runs fully offline using token-based matching.
"""

from __future__ import annotations

import re
from typing import Dict, List, Set, Tuple

# Common tech tokens applymap can recognize in a posting. Matches are
# token-based, so "React" matches "react" but not "reactive".
SKILL_TOKENS = {
    "python", "typescript", "javascript", "java", "go", "rust", "c#", "c++",
    "sql", "postgres", "postgresql", "mysql", "sqlite", "mongodb", "redis",
    "react", "next.js", "nextjs", "node", "node.js", "django", "flask",
    "fastapi", "spring", "spring boot", "angular", "vue", "tailwind",
    "docker", "kubernetes", "k8s", "terraform", "aws", "gcp", "azure",
    "git", "github", "ci/cd", "github actions", "jenkins", "linux",
    "bash", "rest", "graphql", "openapi", "jwt", "oauth",
    "pytest", "jest", "junit", "selenium", "playwright",
    "machine learning", "deep learning", "nlp", "llm", "rag",
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch",
    "agile", "scrum", "jira",
}


def tokenize(text: str) -> Set[str]:
    """Lowercase alphanumeric-ish tokens of the given text."""
    return set(re.findall(r"[a-z0-9][a-z0-9+#./\-]*", text.lower()))


def extract_required_skills(posting: str) -> List[str]:
    """Find recognizable skill tokens inside a job posting.

    Multi-word tokens (e.g. "spring boot") match against the raw text,
    single-word tokens match against tokenized words.
    """
    lowered = posting.lower()
    tokens = tokenize(posting)
    found = []
    for skill in sorted(SKILL_TOKENS):
        if " " in skill or "/" in skill or "." in skill:
            if skill in lowered:
                found.append(skill)
        elif skill in tokens:
            found.append(skill)
    return found


def match(profile_skills: List[str], required: List[str]) -> Dict[str, object]:
    """Compare profile skills against required skills.

    Returns matched and missing skills plus a 0-100 fit score.
    """
    have = set(profile_skills)
    req = list(dict.fromkeys(required))  # de-duplicate, keep order
    matched = [s for s in req if s in have]
    missing = [s for s in req if s not in have]
    score = round(100 * len(matched) / len(req)) if req else 0
    return {
        "score": score,
        "matched": matched,
        "missing": missing,
        "required": req,
    }


def rank_postings(
    profile_skills: List[str], postings: List[Tuple[str, str]]
) -> List[Dict[str, object]]:
    """Rank (label, posting_text) pairs by match score, best first."""
    results = []
    for label, text in postings:
        report = match(profile_skills, extract_required_skills(text))
        report["label"] = label
        results.append(report)
    return sorted(results, key=lambda r: r["score"], reverse=True)
