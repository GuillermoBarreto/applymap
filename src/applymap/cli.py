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
    posting = Path(args.posting).read_text(encoding="utf-8")
    report = matcher.match(prof["skills"], matcher.extract_required_skills(posting))

    print(f"Fit score: {report['score']}/100\n")
    if report["matched"]:
        print("Matched skills:")
        for s in report["matched"]:
            print(f"  + {s}")
    if report["missing"]:
        print("\nMissing skills:")
        for s in report["missing"]:
            print(f"  - {s}")
    if not report["required"]:
        print("(No recognizable tech skills found in the posting.)")
        return 0

    if args.ai:
        if not is_configured():
            print("\nAI features need APPLYMAP_API_KEY. Skipping AI summary.")
            return 0
        print("\n--- AI gap analysis ---")
        print(summarize_gaps(prof, report["missing"]))
    return 0


def cmd_rank(args: argparse.Namespace) -> int:
    prof = profile_mod.load_profile(args.profile)
    postings = []
    for path in args.postings:
        postings.append((Path(path).stem, Path(path).read_text(encoding="utf-8")))
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
    with open(path, "w", newline="", encoding="utf-8") as fh:
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
    posting = Path(args.posting).read_text(encoding="utf-8")
    report = matcher.match(prof["skills"], matcher.extract_required_skills(posting))
    record = {
        "date": datetime.date.today().isoformat(),
        "company": args.company or "",
        "role": args.role or "",
        "posting": args.posting,
        "score": report["score"],
        "matched_skills": report["matched"],
        "missing_skills": report["missing"],
        "status": args.status,
    }
    TRACKING_PATH.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    if TRACKING_PATH.exists():
        entries = json.loads(TRACKING_PATH.read_text(encoding="utf-8"))
    entries.append(record)
    TRACKING_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    print(f"Logged application ({record['date']}, score {record['score']}/100) "
          f"to {TRACKING_PATH}")
    return 0


def cmd_cover_letter(args: argparse.Namespace) -> int:
    if not is_configured():
        print("Cover letters need APPLYMAP_API_KEY set to an OpenAI-compatible key.")
        return 1
    prof = profile_mod.load_profile(args.profile)
    posting = Path(args.posting).read_text(encoding="utf-8")
    letter = draft_cover_letter(prof, posting, args.company, args.role)
    if args.output:
        Path(args.output).write_text(letter + "\n", encoding="utf-8")
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


if __name__ == "__main__":
    raise SystemExit(main())
