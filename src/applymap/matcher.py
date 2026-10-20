"""Deterministic skill matching between a job posting and a user profile.

No API calls here: this runs fully offline using token-based matching.
"""

from __future__ import annotations

import re
from typing import Dict, List, Set, Tuple

# Common tech tokens applymap can recognize in a posting. Matches are
# token-based, so "React" matches "react" but not "reactive". Hyphenated
# spellings (e.g. "rest-api") are covered by SKILL_ALIASES below; the
# tokenizer keeps hyphens inside tokens.
SKILL_TOKENS = {
    "python", "typescript", "javascript", "java", "go", "rust", "c#", "c++",
    "sql", "postgres", "postgresql", "mysql", "sqlite", "mongodb", "redis",
    "react", "react-native", "next.js", "nextjs", "node", "node.js", "django",
    "flask", "fastapi", "spring", "spring boot", "angular", "vue", "tailwind",
    "docker", "kubernetes", "k8s", "terraform", "aws", "gcp", "azure",
    "git", "github", "ci/cd", "github actions", "jenkins", "linux",
    "bash", "rest", "rest-api", "graphql", "openapi", "jwt", "oauth",
    "pytest", "jest", "junit", "selenium", "playwright",
    "machine learning", "deep learning", "nlp", "llm", "rag",
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch",
    "agile", "scrum", "jira",
    "kafka", "rabbitmq", "elasticsearch", "opensearch",
    "s3", "ec2", "lambda", "dynamodb",
    "firebase", "supabase", "vite", "express", "nestjs",
}


# Alternate names that should count as the same skill on both sides of a
# match, e.g. a posting asking for "k8s" matches a profile listing
# "kubernetes". Canonical forms are members of SKILL_TOKENS.
SKILL_ALIASES = {
    "k8s": "kubernetes",
    "js": "javascript",
    "ts": "typescript",
    "postgres": "postgresql",
    "node.js": "node",
    "node-js": "node",
    "next.js": "nextjs",
    "next-js": "nextjs",
    "scikit learn": "scikit-learn",
    "machine-learning": "machine learning",
    "deep-learning": "deep learning",
    "rest-api": "rest",
    "ci-cd": "ci/cd",
    "open-api": "openapi",
    "ci cd": "ci/cd",
    "github actions": "github actions",
    "golang": "go",
    # Fused spellings common in postings: "NodeJS developer".
    "nodejs": "node",
    "reactjs": "react",
    "vuejs": "vue",
}


def canonicalize(skill: str) -> str:
    """Map a skill to its canonical form, resolving aliases."""
    key = skill.strip().lower()
    return SKILL_ALIASES.get(key, key)


def tokenize(text: str) -> Set[str]:
    """Lowercase alphanumeric-ish tokens of the given text."""
    return set(re.findall(r"[a-z0-9][a-z0-9+#./\-]*", text.lower()))


def extract_required_skills(posting: str) -> List[str]:
    """Find recognizable skill tokens inside a job posting.

    Multi-word tokens (e.g. "spring boot") match against the raw text,
    single-word tokens match against tokenized words. Aliases (e.g. "k8s")
    are resolved to their canonical form ("kubernetes"). Hyphenated
    spellings such as "REST-API" or "machine-learning" are matched through
    aliases, since the tokenizer keeps hyphens inside tokens.
    """
    lowered = posting.lower()
    # Strip sentence-final dots: "TS." must tokenize as "ts", not "ts.".
    tokens = {t.rstrip(".") for t in tokenize(posting)}
    found = []
    # Scan both canonical tokens and known aliases; aliases resolve to
    # their canonical form below.
    for skill in sorted(SKILL_TOKENS | set(SKILL_ALIASES)):
        if " " in skill or "/" in skill or "." in skill:
            if skill in lowered:
                found.append(skill)
        elif skill in tokens:
            found.append(skill)
    # Resolve aliases and de-duplicate, keeping sorted order.
    return sorted({canonicalize(s) for s in found})


def skill_mentions(posting: str, required: List[str]) -> Dict[str, int]:
    """Count how often each required skill appears in a posting.

    Alias spellings (e.g. "k8s") count toward their canonical skill
    ("kubernetes"), matching the behavior of extract_required_skills.
    Single-word skills count whole-token occurrences and multi-word
    skills (e.g. "spring boot") count substring occurrences — the same
    rules extract_required_skills uses, so the counts always agree with
    what the extractor found. Skills never mentioned map to 0.
    """
    lowered = posting.lower()
    # Raw token list (not the deduped set from tokenize): duplicates matter
    # for counting.
    tokens = [
        t.rstrip(".")
        for t in re.findall(r"[a-z0-9][a-z0-9+#./\-]*", lowered)
    ]
    # All surface forms that resolve to each canonical skill.
    forms: Dict[str, List[str]] = {}
    for form in sorted(SKILL_TOKENS | set(SKILL_ALIASES)):
        forms.setdefault(canonicalize(form), []).append(form)
    mentions = {}
    for skill in required:
        canon = canonicalize(skill)
        total = 0
        for form in forms.get(canon, [canon]):
            if " " in form or "/" in form or "." in form:
                total += lowered.count(form)
            else:
                total += sum(1 for t in tokens if t == form)
        mentions[skill] = total
    return mentions


def match(profile_skills: List[str], required: List[str]) -> Dict[str, object]:
    """Compare profile skills against required skills.

    Returns matched and missing skills plus a 0-100 fit score. Skill
    aliases (see SKILL_ALIASES) resolve on both sides, so a profile with
    "kubernetes" matches a posting asking for "k8s".
    """
    have = {canonicalize(s) for s in profile_skills}
    req = list(dict.fromkeys(canonicalize(s) for s in required))  # de-duplicate, keep order
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
    """Rank (label, posting_text) pairs by match score, best first.

    Postings tied on score are ordered by mention depth: the total number
    of times the matched skills appear in the posting. A posting that says
    "Python" five times is more about Python than one that says it once,
    so it ranks first among equals. The report dicts themselves are
    unchanged — only the order differs.
    """
    scored = []
    for label, text in postings:
        report = match(profile_skills, extract_required_skills(text))
        report["label"] = label
        mentions = skill_mentions(text, report["required"])
        depth = sum(mentions.get(s, 0) for s in report["matched"])
        scored.append((report, depth))
    scored.sort(key=lambda pair: (pair[0]["score"], pair[1]), reverse=True)
    return [report for report, _ in scored]
