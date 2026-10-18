"""applymap command-line interface."""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import sys
from pathlib import Path

from . import __version__, matcher, profile as profile_mod
from .llm import draft_cover_letter, is_configured, summarize_gaps


def _read_posting(path: str) -> str:
    """Read a posting file, with a friendly error when it is missing."""
    resolved = Path(path).expanduser()
    try:
        return resolved.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Posting file not found: {resolved}. Check the path and try again."
        )


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
        print(json.dumps(report, indent=2))
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
    if not report["required"]:
        print("(No recognizable tech skills found in the posting.)")
        return 0

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


def cmd_rank(args: argparse.Namespace) -> int:
    prof = profile_mod.load_profile(args.profile)
    postings = []
    for path in args.postings:
        postings.append((Path(path).stem, _read_posting(path)))
    ranked = matcher.rank_postings(prof["skills"], postings)
    for r in ranked:
        print(f"{r['score']:>3}/100  {r['label']}  "
              f"({len(r['matched'])}/{len(r['required'])} skills)")
    if args.csv:
        _write_rank_csv(args.csv, ranked)
        print(f"Wrote ranking to {args.csv}")
    return 0


def _write_rank_csv(path: str, ranked: list) -> None:
    """Write ranked posting results to a CSV file for spreadsheets."""
    out = Path(path)
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


def cmd_track(args: argparse.Namespace) -> int:
    """Log an application: date, company, role, and this profile's fit score."""
    prof = profile_mod.load_profile(args.profile)
    posting = _read_posting(args.posting)
    # Store the posting as an absolute path so the record still points at
    # the right file when applymap runs from a different directory.
    posting_path = str(Path(args.posting).expanduser().resolve())
    report = matcher.match(prof["skills"], matcher.extract_required_skills(posting))
    record = {
        "date": datetime.date.today().isoformat(),
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
    TRACKING_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    print(f"Logged application ({record['date']}, score {record['score']}/100) "
          f"to {TRACKING_PATH}")
    return 0


def _norm_identity(value: str) -> str:
    """Normalize a company/role name for duplicate detection.

    Company names typed as "Acme", "acme", or "  Acme " are the same
    application; compare case- and whitespace-insensitively.
    """
    return (value or "").strip().casefold()


def _already_tracked(entries: list, posting_path: str, company: str, role: str) -> bool:
    """True when this exact application is already logged; warns the user."""
    company, role = _norm_identity(company), _norm_identity(role)
    for entry in entries:
        if (entry.get("posting") == posting_path
                and _norm_identity(entry.get("company")) == company
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
    if not entries:
        if args.status:
            print(f"No applications with status '{args.status}' tracked yet.")
        else:
            print("No applications tracked yet. Log one with `applymap track`.")
        return 0
    for e in reversed(entries):
        company = e.get("company") or "(unknown company)"
        role = e.get("role") or "(unknown role)"
        print(f"{e.get('date', '?')}  {e.get('score', '?')}/100  "
              f"{company} — {role}  [{e.get('status', '?')}]")
    print(f"\n{len(entries)} application(s) tracked.")
    return 0


def cmd_cover_letter(args: argparse.Namespace) -> int:
    if not is_configured():
        print("Cover letters need APPLYMAP_API_KEY set to an OpenAI-compatible key.")
        return 1
    prof = profile_mod.load_profile(args.profile)
    posting = _read_posting(args.posting)
    letter = draft_cover_letter(prof, posting, args.company, args.role)
    if args.output:
        out = Path(args.output)
        # Like `rank --csv`: don't fail when the target folder doesn't exist yet.
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(letter + "\n", encoding="utf-8")
        print(f"Wrote cover letter to {args.output}")
    else:
        print(letter)
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
    pt.set_defaults(func=cmd_track)

    ps = sub.add_parser("applications", help="List tracked applications.")
    ps.add_argument("--status", default=None,
                    choices=["interested", "applied", "interview", "offer", "rejected"],
                    help="Only show applications with this status.")
    ps.set_defaults(func=cmd_applications)

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
