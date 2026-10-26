"""applymap command-line interface."""

from __future__ import annotations

import argparse
import csv
import datetime
import difflib
import json
import os
import sys
import tempfile
from pathlib import Path

from . import __version__, matcher, profile as profile_mod
from .llm import draft_cover_letter, is_configured, summarize_gaps


# Posting files are plain text: cap what _read_posting loads so a huge
# file passed by mistake doesn't eat all memory. Tests shrink this.
MAX_POSTING_CHARS = 1_000_000


def _read_posting(path: str) -> str:
    """Read a posting file, with a friendly error when it is missing.

    Posting files are plain text, so anything above ~1MB is almost
    certainly a mistake (e.g. a log file passed instead of a posting).
    Overlong files are truncated with a warning rather than read fully
    into memory, so analyze/rank/track still work on the text that
    matters.
    """
    resolved = Path(path).expanduser()
    try:
        with open(resolved, "r", encoding="utf-8") as fh:
            text = fh.read(MAX_POSTING_CHARS + 1)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Posting file not found: {resolved}. Check the path and try again."
        )
    except UnicodeDecodeError:
        raise RuntimeError(
            f"Posting file {resolved} is not valid UTF-8 text. "
            "Save it as plain UTF-8 text and try again."
        )
    except OSError as exc:
        # IsADirectoryError ("applymap analyze ~/postings/") or a
        # PermissionError would otherwise dump a traceback; main()
        # already turns RuntimeError into a friendly message.
        raise RuntimeError(
            f"Cannot read posting file {resolved}: "
            f"{exc.strerror or exc}."
        ) from exc
    if len(text) > MAX_POSTING_CHARS:
        print(f"Warning: {resolved} is over {MAX_POSTING_CHARS:,} characters; "
              f"using only the first {MAX_POSTING_CHARS:,} — this is probably "
              "not a job posting.")
        text = text[:MAX_POSTING_CHARS]
    return text


def cmd_init_profile(args: argparse.Namespace) -> int:
    path = Path(args.path or str(profile_mod.DEFAULT_PROFILE_PATH)).expanduser()
    if path.exists() and not args.force:
        print(f"Profile already exists at {path} (use --force to overwrite).")
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    template = (
        "# applymap profile — your real skills and background. Keep it honest;\n"
        "# every cover letter and score is derived from this file.\n"
        "name: Your Name\n"
        "headline: B.S. Software Engineering student, IT support technician\n"
        "location: Chicago, IL\n"
        "target_roles:\n"
        "  - Software Development Engineer\n"
        "  - Backend Developer\n"
        "skills:\n"
        "  - python\n"
        "  - javascript\n"
        "  - typescript\n"
        "  - react\n"
        "  - sql\n"
        "  - git\n"
        "  - linux\n"
        "  - docker\n"
        "  - fastapi\n"
        "experience:\n"
        "  - Resolved 2,579 support tickets across switches, routers, and access points\n"
        "  - Automated routine tasks with Python scripts, saving ~31 hours/week\n"
    )
    path.write_text(template, encoding="utf-8")
    print(f"Created profile template at {path}. Edit it with your real details.")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    prof = profile_mod.load_profile(args.profile)
    posting = _read_posting(args.posting)
    required = matcher.extract_required_skills(posting)
    report = matcher.match(prof["skills"], required)
    report["mentions"] = matcher.skill_mentions(posting, required)

    if args.json:
        # Machine-readable output for scripting (e.g. piping into jq).
        if args.ai:
            # --ai used to be silently ignored alongside --json (issue #12):
            # the gap analysis now rides along as a field, or null with a
            # warning when it can't run.
            if is_configured() and report["missing"]:
                report["gap_analysis"] = summarize_gaps(prof, report["missing"])
            else:
                report["gap_analysis"] = None
                reason = (
                    "no missing skills to analyze"
                    if not report["missing"]
                    else "APPLYMAP_API_KEY is not set"
                )
                print(f"Warning: --ai had no effect ({reason}).",
                      file=sys.stderr)
        print(json.dumps(report, indent=2))
        return 0

    if report["score"] is None:
        # No recognizable skills (issue #10): printing "Fit score: 0/100"
        # here would be indistinguishable from a posting that matched
        # nothing.
        print("(No recognizable tech skills found in the posting — "
              "the fit score is not meaningful.)")
        return 0

    print(f"Fit score: {report['score']}/100\n")
    if report["matched"]:
        print("Matched skills:")
        for s in report["matched"]:
            print(f"  + {s} (mentioned {report['mentions'][s]}x)")
    if report["missing"]:
        print("\nMissing skills:")
        for s in report["missing"]:
            print(f"  - {s} (mentioned {report['mentions'][s]}x)")

    if args.ai:
        if not is_configured():
            print("\nAI features need APPLYMAP_API_KEY. Skipping AI summary.")
            return 0
        if not report["missing"]:
            # Nothing to analyze — skip the paid API call entirely.
            print("\nNo missing skills — nothing for the AI gap analysis to cover.")
            return 0
        print("\n--- AI gap analysis ---")
        print(summarize_gaps(prof, report["missing"]))
    return 0


def _unique_labels(postings: list) -> list:
    """(label, text) pairs with a unique label for every posting.

    cmd_rank labels postings by filename stem, so backend.txt in two
    different folders prints as two identical rows. Suffix later copies
    with (2), (3), ... so every ranking row maps back to its file.
    """
    seen: dict = {}
    labeled = []
    for path, text in postings:
        stem = Path(path).stem
        seen[stem] = seen.get(stem, 0) + 1
        label = stem if seen[stem] == 1 else f"{stem} ({seen[stem]})"
        labeled.append((label, text))
    return labeled


def cmd_rank(args: argparse.Namespace) -> int:
    prof = profile_mod.load_profile(args.profile)
    postings = []
    for path in args.postings:
        postings.append((path, _read_posting(path)))
    ranked = matcher.rank_postings(prof["skills"], _unique_labels(postings))
    # A None score (no recognizable skills, issue #10) is not comparable
    # to --min-score: it always shows, sorted last, as "n/a".
    hidden = [r for r in ranked
              if r["score"] is not None and r["score"] < args.min_score]
    ranked = [r for r in ranked
              if r["score"] is None or r["score"] >= args.min_score]
    if args.json:
        # Machine-readable output for scripting (e.g. piping into jq).
        print(json.dumps(ranked, indent=2))
    else:
        for r in ranked:
            score_txt = (f"{r['score']:>3}/100"
                         if r["score"] is not None else "  n/a")
            print(f"{score_txt}  {r['label']}  "
                  f"({len(r['matched'])}/{len(r['required'])} skills)")
        if hidden:
            print(f"({len(hidden)} posting(s) below --min-score {args.min_score} hidden)")
    if args.csv:
        _write_rank_csv(args.csv, ranked)
        print(f"Wrote ranking to {args.csv}")
    return 0


def _write_rank_csv(path: str, ranked: list) -> None:
    """Write ranked posting results to a CSV file for spreadsheets."""
    # Expand ~ like the posting inputs do, so `--csv ~/reports/r.csv`
    # doesn't create a literal "~" directory.
    out = Path(path).expanduser()
    # So `--csv reports/ranking.csv` works without pre-creating the folder.
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["label", "score", "matched_count", "required_count",
             "matched_skills", "missing_skills"]
        )
        for r in ranked:
            writer.writerow([
                r["label"],
                r["score"],
                len(r["matched"]),
                len(r["required"]),
                "; ".join(r["matched"]),
                "; ".join(r["missing"]),
            ])


TRACKING_PATH = (
    Path(os.environ.get("APPLYMAP_DATA_DIR", "~/.applymap")).expanduser()
    / "applications.json"
)


def _save_applications(entries: list) -> None:
    """Persist the tracked log atomically: temp file + os.replace.

    A plain write_text can leave applications.json half-written (and the
    whole log unreadable) if the process is killed mid-write. Writing to
    a temp file in the same directory first makes the swap one
    filesystem operation. A failed write removes the temp file instead
    of leaving a corrupt log behind.
    """
    TRACKING_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=TRACKING_PATH.parent, prefix=".applications-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(entries, fh, indent=2)
        os.replace(tmp_name, TRACKING_PATH)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _track_date(value: str | None) -> str:
    """The date to stamp on a tracked application.

    Defaults to today; accepts an explicit YYYY-MM-DD for backfilling
    applications sent before tracking started (followup and stats date
    math depend on real dates). Malformed and future dates are rejected
    with a friendly error instead of logging nonsense.
    """
    if not value:
        return datetime.date.today().isoformat()
    try:
        parsed = datetime.date.fromisoformat(value)
    except ValueError:
        raise RuntimeError(
            f"--date {value!r} is not a valid date; use YYYY-MM-DD."
        )
    if parsed > datetime.date.today():
        raise RuntimeError(
            f"--date {value!r} is in the future; log the application on the "
            "day you actually applied."
        )
    return parsed.isoformat()


def cmd_track(args: argparse.Namespace) -> int:
    """Log an application: date, company, role, and this profile's fit score."""
    prof = profile_mod.load_profile(args.profile)
    posting = _read_posting(args.posting)
    # Store the posting as an absolute path so the record still points at
    # the right file when applymap runs from a different directory.
    posting_path = str(Path(args.posting).expanduser().resolve())
    report = matcher.match(prof["skills"], matcher.extract_required_skills(posting))
    if not report["required"]:
        # A None score from "no recognizable skills" is not a real
        # mismatch — say so instead of logging a meaningless score.
        print("(No recognizable tech skills found in the posting — "
              "no fit score was recorded.)")
    record = {
        "date": _track_date(args.date),
        "company": args.company or "",
        "role": args.role or "",
        "posting": posting_path,
        "score": report["score"],
        "matched_skills": report["matched"],
        "missing_skills": report["missing"],
        "status": args.status,
    }
    TRACKING_PATH.parent.mkdir(parents=True, exist_ok=True)
    entries = _load_applications()  # friendly error on corrupted log, not a traceback
    if _already_tracked(entries, posting_path, args.company or "", args.role or ""):
        return 0
    entries.append(record)
    _save_applications(entries)
    score_txt = (f"{record['score']}/100"
                 if isinstance(record["score"], (int, float)) else "n/a")
    print(f"Logged application ({record['date']}, score {score_txt}) "
          f"to {TRACKING_PATH}")
    return 0


def _norm_identity(value: str) -> str:
    """Normalize a company/role name for duplicate detection.

    Company names typed as "Acme", "acme", or "  Acme " are the same
    application; compare case- and whitespace-insensitively.
    """
    return (value or "").strip().casefold()


def _posting_key(value: str) -> str:
    """Normalize a posting path for duplicate detection (issue #20).

    New entries store absolute paths, but entries logged before that
    change (or hand-edited logs) keep whatever string was passed —
    typically a relative "posting.txt". Resolving against the current
    directory maps both spellings to the same file so the dedup check
    still recognizes it.
    """
    return str(Path(value or "").expanduser().resolve())


def _already_tracked(entries: list, posting_path: str, company: str, role: str) -> bool:
    """True when this exact application is already logged; warns the user."""
    company, role = _norm_identity(company), _norm_identity(role)
    base = Path(posting_path).name
    for entry in entries:
        stored = entry.get("posting") or ""
        # The bare-name fallback covers entries logged from a different
        # directory, where no absolute spelling can ever match.
        if (_posting_key(stored) != posting_path
                and Path(stored).name != base):
            continue
        if (_norm_identity(entry.get("company")) == company
                and _norm_identity(entry.get("role")) == role):
            print(
                f"Already tracking {company or 'this posting'}"
                f"{' — ' + role if role else ''} "
                f"(logged {entry.get('date', 'on an unknown date')}). "
                "Skipping the duplicate."
            )
            return True
    return False


def _load_applications() -> list:
    """Read the tracked applications log as a list of records.

    Returns an empty list when nothing has been tracked yet. Raises a
    friendly RuntimeError (instead of a traceback) when the log exists
    but is corrupted or not shaped like a list.
    """
    if not TRACKING_PATH.exists():
        return []
    try:
        entries = json.loads(TRACKING_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise RuntimeError(
            f"Applications log at {TRACKING_PATH} is not valid JSON. "
            "Fix or remove the file, then try again."
        )
    if not isinstance(entries, list):
        raise RuntimeError(
            f"Applications log at {TRACKING_PATH} should be a JSON list of "
            f"records, but contains {type(entries).__name__}."
        )
    return entries


def cmd_applications(args: argparse.Namespace) -> int:
    """List tracked applications, newest first, optionally filtered by status."""
    entries = _load_applications()
    if args.status:
        entries = [e for e in entries if e.get("status") == args.status]
    # Newest first, same order as the text listing below — the JSON
    # output used to come back in raw insertion order, which disagreed
    # with what `applications` prints.
    entries = sorted(entries, key=lambda e: e.get("date") or "", reverse=True)
    if args.json:
        # Machine-readable output for scripting (e.g. piping into jq).
        print(json.dumps(entries, indent=2))
        return 0
    if not entries:
        if args.status:
            print(f"No applications with status '{args.status}' tracked yet.")
        else:
            print("No applications tracked yet. Log one with `applymap track`.")
        return 0
    for e in sorted(entries, key=lambda e: e.get("date") or "", reverse=True):
        company = e.get("company") or "(unknown company)"
        role = e.get("role") or "(unknown role)"
        # A null score means the posting had no recognizable skills when
        # it was tracked (issue #10) — "n/a", never "None/100".
        score = e.get("score")
        score_txt = f"{score}/100" if isinstance(score, (int, float)) else "n/a"
        print(f"{e.get('date', '?')}  {score_txt}  "
              f"{company} — {role}  [{e.get('status', '?')}]")
    print(f"\n{len(entries)} application(s) tracked.")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Write tracked applications to a CSV or JSON file for spreadsheets/scripts."""
    entries = _load_applications()
    if args.status:
        entries = [e for e in entries if e.get("status") == args.status]
    # Expand ~ like `rank --csv`, so `--csv ~/apps.csv` doesn't create a
    # literal "~" directory; create missing parent folders too.
    out = Path(args.csv).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.format == "json":
        out.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    else:
        with open(out, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "date", "company", "role", "status", "score",
                "matched_skills", "missing_skills", "posting",
            ])
            for e in entries:
                writer.writerow([
                    e.get("date", ""),
                    e.get("company", ""),
                    e.get("role", ""),
                    e.get("status", ""),
                    e.get("score", ""),
                    "; ".join(e.get("matched_skills", [])),
                    "; ".join(e.get("missing_skills", [])),
                    e.get("posting", ""),
                ])
    print(f"Wrote {len(entries)} application(s) to {args.csv} ({args.format})")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    """Print a summary of tracked applications: totals, status counts, best fit."""
    entries = _load_applications()
    if not entries:
        print("No applications tracked yet. Log one with `applymap track`.")
        return 0
    counts: dict = {}
    for e in entries:
        status = e.get("status") or "(unknown)"
        counts[status] = counts.get(status, 0) + 1
    scores = [
        e["score"] for e in entries
        if isinstance(e.get("score"), (int, float))
    ]
    print(f"{len(entries)} application(s) tracked.\n")
    print("By status:")
    for status in sorted(counts):
        print(f"  {status}: {counts[status]}")
    if scores:
        avg = round(sum(scores) / len(scores))
        best = max(
            entries,
            key=lambda e: e.get("score")
            if isinstance(e.get("score"), (int, float)) else -1,
        )
        company = best.get("company") or "(unknown company)"
        role = best.get("role") or "(unknown role)"
        print(f"\nAverage fit score: {avg}/100")
        print(f"Best fit: {company} — {role} ({best.get('score')}/100)")
    _print_funnel(counts)
    return 0


def _print_funnel(counts: dict) -> None:
    """Print applied -> interview -> offer conversion rates.

    An offer implies an interview, so interviews include offers. Only
    counts statuses that represent real pipeline movement; "interested"
    entries are wishlists, not applications, and are excluded.
    """
    applied = counts.get("applied", 0)
    interviews = counts.get("interview", 0) + counts.get("offer", 0)
    offers = counts.get("offer", 0)
    pipeline = applied + counts.get("interview", 0) + offers + counts.get("rejected", 0)
    if not pipeline:
        return
    print("\nConversion funnel (applied -> interview -> offer):")
    print(f"  {applied} applied, {interviews} reached interview, {offers} offers")
    print(f"  interview rate: {round(100 * interviews / pipeline)}% of {pipeline}")
    if interviews:
        print(f"  offer rate: {round(100 * offers / interviews)}% of interviews")


def _resolve_posting_selector(value: str) -> str:
    """Resolve an --posting selector to something comparable against records.

    A path to an existing file becomes its absolute path (matching what
    `track` stores); anything else becomes a bare filename, so the user
    can type just ``posting-b.txt``.
    """
    resolved = Path(value).expanduser()
    if resolved.exists():
        return str(resolved.resolve())
    return Path(value).name


def _find_application_indexes(
    entries: list, company: str, role: str, posting: str | None = None
) -> list:
    """Indexes of entries matching the company/role, normalized like _already_tracked.

    When ``posting`` is given, only entries tracked from that posting file
    count — the escape hatch when company+role alone matches several
    applications (re-applied under a new requisition, see issue #18).
    """
    company, role = _norm_identity(company), _norm_identity(role)
    selector = _resolve_posting_selector(posting) if posting else None
    matched = []
    for i, entry in enumerate(entries):
        if (_norm_identity(entry.get("company")) != company
                or _norm_identity(entry.get("role")) != role):
            continue
        if selector is not None:
            stored = entry.get("posting") or ""
            if not (stored == selector or Path(stored).name == selector):
                continue
        matched.append(i)
    return matched


def cmd_update_status(args: argparse.Namespace) -> int:
    """Change the status of a tracked application, e.g. applied -> interview."""
    entries = _load_applications()
    matches = _find_application_indexes(
        entries, args.company, args.role, args.posting
    )
    if not matches:
        hint = (
            f" from '{args.posting}'" if args.posting else ""
        )
        print(f"No tracked application for '{args.company}' — '{args.role}'"
              f"{hint}. Log it first with `applymap track`.")
        return 1
    if len(matches) > 1:
        print(f"Multiple applications match '{args.company}' — '{args.role}':")
        for i in matches:
            e = entries[i]
            score = e.get("score")
            score_txt = (f"{score}/100"
                         if isinstance(score, (int, float)) else "n/a")
            print(f"  {e.get('date', '?')}  {score_txt}  "
                  f"[{e.get('status', '?')}]  {e.get('posting', '?')}")
        print("Re-run with --posting <posting file> to pick one.")
        return 1
    entries[matches[0]]["status"] = args.status
    _save_applications(entries)
    print(f"Updated {args.company} — {args.role} to status '{args.status}'.")
    return 0


def cmd_untrack(args: argparse.Namespace) -> int:
    """Remove a tracked application from the log.

    Matches entries exactly like update-status (see
    _find_application_indexes), including the --posting escape hatch for
    company+role duplicates. The log is rewritten atomically, like every
    other write.
    """
    entries = _load_applications()
    matches = _find_application_indexes(
        entries, args.company, args.role, args.posting
    )
    if not matches:
        hint = (
            f" from '{args.posting}'" if args.posting else ""
        )
        print(f"No tracked application for '{args.company}' — '{args.role}'"
              f"{hint}. Nothing to remove.")
        return 1
    if len(matches) > 1:
        print(f"Multiple applications match '{args.company}' — '{args.role}':")
        for i in matches:
            e = entries[i]
            print(f"  {e.get('date', '?')}  "
                  f"[{e.get('status', '?')}]  {e.get('posting', '?')}")
        print("Re-run with --posting <posting file> to pick one.")
        return 1
    removed = entries.pop(matches[0])
    _save_applications(entries)
    company = removed.get("company") or "(unknown company)"
    role = removed.get("role") or "(unknown role)"
    print(f"Removed {company} — {role} "
          f"(logged {removed.get('date', 'on an unknown date')}).")
    return 0


def cmd_followup(args: argparse.Namespace) -> int:
    """List applications still waiting for a response after --days days."""
    entries = _load_applications()
    today = datetime.date.today()
    stale = []
    for e in entries:
        if e.get("status") != "applied":
            continue
        try:
            logged = datetime.date.fromisoformat(e.get("date") or "")
        except (ValueError, TypeError):
            # A hand-edited record with a bad date is still tracked — skip
            # it here rather than crashing the whole report.
            continue
        waiting = (today - logged).days
        if waiting >= args.days:
            stale.append((waiting, e))
    if not stale:
        print(f"No applications waiting {args.days}+ days. All caught up.")
        return 0
    stale.sort(key=lambda pair: pair[0], reverse=True)  # longest waiting first
    print(f"{len(stale)} application(s) waiting {args.days}+ days — "
          f"time to follow up:\n")
    for waiting, e in stale:
        company = e.get("company") or "(unknown company)"
        role = e.get("role") or "(unknown role)"
        print(f"  {waiting}d  {company} — {role} (logged {e.get('date')})")
    return 0


def cmd_cover_letter(args: argparse.Namespace) -> int:
    if not is_configured():
        print("Cover letters need APPLYMAP_API_KEY set to an OpenAI-compatible key.")
        return 1
    prof = profile_mod.load_profile(args.profile)
    posting = _read_posting(args.posting)
    letter = draft_cover_letter(prof, posting, args.company, args.role)
    if args.output:
        # Expand ~ like the posting inputs do (see _read_posting), so
        # `--output ~/letters/acme.md` doesn't create a literal "~" dir.
        out = Path(args.output).expanduser()
        # Like `rank --csv`: don't fail when the target folder doesn't exist yet.
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(letter + "\n", encoding="utf-8")
        print(f"Wrote cover letter to {args.output}")
    else:
        print(letter)
    return 0


def _score_type(value: str) -> int:
    """argparse type for 0-100 score thresholds like --min-score."""
    try:
        score = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer")
    if not 0 <= score <= 100:
        raise argparse.ArgumentTypeError(f"{value!r} is not between 0 and 100")
    return score


def _days_type(value: str) -> int:
    """argparse type for --days: a non-negative integer.

    A negative threshold would flag every tracked application, so it is
    rejected up front with a friendly error instead of silently
    matching everything.
    """
    try:
        days = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer")
    if days < 0:
        raise argparse.ArgumentTypeError(
            f"{value!r} is negative; --days needs 0 or more"
        )
    return days


def cmd_check_profile(args: argparse.Namespace) -> int:
    """Validate the profile and report gaps the matcher and AI need filled.

    Exits 1 when anything is missing so it can gate scripts; exits 0
    with "Profile looks good." when the profile is complete.
    """
    prof = profile_mod.load_profile(args.profile)
    warnings = []
    if not prof.get("name"):
        warnings.append(
            "name is empty — set it so cover letters address you correctly."
        )
    if not prof.get("headline"):
        warnings.append(
            "headline is empty — one line about who you are sharpens AI prompts."
        )
    skills = prof.get("skills", [])
    if not skills:
        warnings.append(
            "no skills listed — analyze has no fit score to report and "
            "track records n/a."
        )
    else:
        unknown = [
            s for s in skills
            if matcher.canonicalize(s) not in matcher.SKILL_TOKENS
        ]
        if unknown:
            # Point at the likely intended spelling when one is obvious —
            # "typscript" is almost certainly a typo for "typescript".
            hints = []
            for skill in unknown:
                close = difflib.get_close_matches(
                    skill, matcher.SKILL_TOKENS, n=1, cutoff=0.75
                )
                hints.append(
                    skill + (f" (did you mean '{close[0]}'?)" if close else "")
                )
            warnings.append(
                "these skills aren't in the matcher's vocabulary and will "
                f"never match a posting: {', '.join(hints)}"
            )
    if not prof.get("target_roles"):
        warnings.append("no target_roles listed — add the roles you're aiming for.")
    if not prof.get("experience"):
        warnings.append(
            "no experience entries — cover letters are built from these facts."
        )
    if warnings:
        print("Profile issues found:")
        for w in warnings:
            print(f"  - {w}")
        return 1
    print("Profile looks good.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="applymap",
        description="Score job postings against your profile; draft honest cover letters.",
    )
    p.add_argument("--version", action="version", version=f"applymap {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    pi = sub.add_parser("init-profile", help="Create a profile template.")
    pi.add_argument("--path", default=None)
    pi.add_argument("--force", action="store_true")
    pi.set_defaults(func=cmd_init_profile)

    pk = sub.add_parser("check-profile", help="Validate your profile for gaps.")
    pk.add_argument("--profile", default=None)
    pk.set_defaults(func=cmd_check_profile)

    pa = sub.add_parser("analyze", help="Score one posting against your profile.")
    pa.add_argument("posting", help="Path to the job posting text file.")
    pa.add_argument("--profile", default=None)
    pa.add_argument("--ai", action="store_true", help="Add AI gap analysis (needs API key).")
    pa.add_argument("--json", action="store_true",
                    help="Print the fit report as JSON instead of text.")
    pa.set_defaults(func=cmd_analyze)

    pr = sub.add_parser("rank", help="Rank several postings by fit score.")
    pr.add_argument("postings", nargs="+", help="Paths to posting text files.")
    pr.add_argument("--profile", default=None)
    pr.add_argument("--csv", default=None, metavar="PATH",
                    help="Also write the ranking to a CSV file.")
    pr.add_argument("--min-score", default=0, type=_score_type, metavar="0-100",
                    help="Hide postings scoring below this fit score.")
    pr.add_argument("--json", action="store_true",
                    help="Print the ranking as JSON instead of text.")
    pr.set_defaults(func=cmd_rank)

    pc = sub.add_parser("cover-letter", help="Draft a tailored cover letter (needs API key).")
    pc.add_argument("posting", help="Path to the job posting text file.")
    pc.add_argument("--company", required=True)
    pc.add_argument("--role", required=True)
    pc.add_argument("--profile", default=None)
    pc.add_argument("--output", "-o", default=None)
    pc.set_defaults(func=cmd_cover_letter)

    pt = sub.add_parser("track", help="Log an application with its fit score.")
    pt.add_argument("posting", help="Path to the job posting text file.")
    pt.add_argument("--profile", default=None)
    pt.add_argument("--company", default="", help="Company name.")
    pt.add_argument("--role", default="", help="Role title.")
    pt.add_argument("--status", default="applied",
                    choices=["interested", "applied", "interview", "offer", "rejected"],
                    help="Application status.")
    pt.add_argument("--date", default=None, metavar="YYYY-MM-DD",
                    help="Log the application under this date (default: today); "
                         "use when backfilling applications you sent earlier.")
    pt.set_defaults(func=cmd_track)

    pu = sub.add_parser("update-status", help="Change a tracked application's status.")
    pu.add_argument("--company", required=True, help="Company name (matches track --company).")
    pu.add_argument("--role", required=True, help="Role title (matches track --role).")
    pu.add_argument("--status", required=True,
                    choices=["interested", "applied", "interview", "offer", "rejected"],
                    help="New status.")
    pu.add_argument("--posting", default=None, metavar="FILE",
                    help="Only match the application tracked from this posting file; "
                         "use when company+role alone matches more than one.")
    pu.set_defaults(func=cmd_update_status)

    prm = sub.add_parser("untrack", help="Remove a tracked application.")
    prm.add_argument("--company", required=True, help="Company name (matches track --company).")
    prm.add_argument("--role", required=True, help="Role title (matches track --role).")
    prm.add_argument("--posting", default=None, metavar="FILE",
                    help="Only remove the application tracked from this posting file; "
                         "use when company+role alone matches more than one.")
    prm.set_defaults(func=cmd_untrack)

    ps = sub.add_parser("applications", help="List tracked applications.")
    ps.add_argument("--status", default=None,
                    choices=["interested", "applied", "interview", "offer", "rejected"],
                    help="Only show applications with this status.")
    ps.add_argument("--json", action="store_true",
                    help="Print the tracked records as JSON instead of text.")
    ps.set_defaults(func=cmd_applications)

    pst = sub.add_parser("stats", help="Summarize tracked applications.")
    pst.set_defaults(func=cmd_stats)

    pe = sub.add_parser("export", help="Export tracked applications to CSV or JSON.")
    pe.add_argument("--csv", required=True, metavar="PATH",
                    help="File to write (creates parent folders).")
    pe.add_argument("--status", default=None,
                    choices=["interested", "applied", "interview", "offer", "rejected"],
                    help="Only export applications with this status.")
    pe.add_argument("--format", default="csv", choices=["csv", "json"],
                    help="Export format (default: csv).")
    pe.set_defaults(func=cmd_export)

    pf = sub.add_parser("followup", help="Find applications waiting too long for a response.")
    pf.add_argument("--days", type=_days_type, default=30, metavar="N",
                    help="Flag applications in 'applied' status for at least N days (default: 30).")
    pf.set_defaults(func=cmd_followup)

    return p


def main(argv: list | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        # Ctrl+C during a long AI call should exit quietly, not dump a traceback.
        print(file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
