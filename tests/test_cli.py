import yaml

from applymap.cli import build_parser, main


def _write_profile_and_posting(tmp_path):
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        yaml.safe_dump(
            {
                "name": "Test Dev",
                "headline": "Software engineering student",
                "skills": ["python", "sql", "docker"],
                "experience": ["automated deployments"],
            }
        ),
        encoding="utf-8",
    )
    posting_path = tmp_path / "posting.txt"
    posting_path.write_text(
        "Backend developer: Python, SQL, and Kubernetes experience required.",
        encoding="utf-8",
    )
    return profile_path, posting_path


def test_analyze_reports_score(tmp_path, capsys):
    profile_path, posting_path = _write_profile_and_posting(tmp_path)
    rc = main(["analyze", str(posting_path), "--profile", str(profile_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Fit score:" in out
    assert "python" in out
    assert "kubernetes" in out


def test_analyze_without_ai_key_skips_ai(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("APPLYMAP_API_KEY", raising=False)
    profile_path, posting_path = _write_profile_and_posting(tmp_path)
    rc = main(["analyze", str(posting_path), "--profile", str(profile_path), "--ai"])
    assert rc == 0
    assert "APPLYMAP_API_KEY" in capsys.readouterr().out


def test_cover_letter_requires_key(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("APPLYMAP_API_KEY", raising=False)
    profile_path, posting_path = _write_profile_and_posting(tmp_path)
    rc = main(
        [
            "cover-letter",
            str(posting_path),
            "--company",
            "Acme",
            "--role",
            "Backend Dev",
            "--profile",
            str(profile_path),
        ]
    )
    assert rc == 1
    assert "APPLYMAP_API_KEY" in capsys.readouterr().out


def test_rank_orders_postings(tmp_path, capsys):
    profile_path, _ = _write_profile_and_posting(tmp_path)
    good = tmp_path / "good.txt"
    good.write_text("Python and SQL developer.", encoding="utf-8")
    bad = tmp_path / "bad.txt"
    bad.write_text("Rust and Kubernetes engineer.", encoding="utf-8")
    rc = main(["rank", str(good), str(bad), "--profile", str(profile_path)])
    assert rc == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "good" in lines[0]
    assert "bad" in lines[1]


def test_main_handles_keyboard_interrupt(monkeypatch):
    import argparse

    from applymap import cli as cli_mod

    def raiser(args):
        raise KeyboardInterrupt()

    parser = argparse.ArgumentParser()
    parser.set_defaults(func=raiser)
    monkeypatch.setattr(cli_mod, "build_parser", lambda: parser)
    assert main([]) == 130


def test_parser_has_subcommands():
    parser = build_parser()
    subparsers = parser._subparsers._group_actions[0]
    for cmd in ("init-profile", "analyze", "rank", "cover-letter"):
        assert cmd in subparsers.choices
        assert callable(subparsers.choices[cmd].get_default("func"))


def test_rank_csv_export(tmp_path):
    import csv

    profile_path, _ = _write_profile_and_posting(tmp_path)
    good = tmp_path / "good.txt"
    good.write_text("Python and SQL developer.", encoding="utf-8")
    bad = tmp_path / "bad.txt"
    bad.write_text("Rust and Kubernetes engineer.", encoding="utf-8")
    csv_path = tmp_path / "rank.csv"
    rc = main(
        [
            "rank",
            str(good),
            str(bad),
            "--profile",
            str(profile_path),
            "--csv",
            str(csv_path),
        ]
    )
    assert rc == 0
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2
    assert rows[0]["label"] == "good"
    assert int(rows[0]["score"]) >= int(rows[1]["score"])
    assert "python" in rows[0]["matched_skills"]
    assert "kubernetes" in rows[1]["missing_skills"]


def test_rank_csv_creates_parent_dirs(tmp_path):
    profile_path, _ = _write_profile_and_posting(tmp_path)
    good = tmp_path / "good.txt"
    good.write_text("Python and SQL developer.", encoding="utf-8")
    csv_path = tmp_path / "reports" / "rank.csv"
    rc = main(
        ["rank", str(good), "--profile", str(profile_path),
         "--csv", str(csv_path)]
    )
    assert rc == 0
    assert csv_path.exists()


def test_track_logs_application(tmp_path, monkeypatch, capsys):
    import json
    from applymap import cli as cli_mod

    monkeypatch.setattr(cli_mod, "TRACKING_PATH", tmp_path / "applications.json")
    profile_path, posting_path = _write_profile_and_posting(tmp_path)
    rc = main(
        [
            "track",
            str(posting_path),
            "--profile",
            str(profile_path),
            "--company",
            "Acme",
            "--role",
            "Backend Dev",
        ]
    )
    assert rc == 0
    entries = json.loads((tmp_path / "applications.json").read_text(encoding="utf-8"))
    assert len(entries) == 1
    record = entries[0]
    assert record["company"] == "Acme"
    assert record["role"] == "Backend Dev"
    assert record["status"] == "applied"
    assert record["score"] == 67  # python + sql of python/sql/kubernetes
    assert "kubernetes" in record["missing_skills"]
    assert "Logged application" in capsys.readouterr().out


def test_track_appends_to_existing_log(tmp_path, monkeypatch):
    import json
    from applymap import cli as cli_mod

    log = tmp_path / "applications.json"
    log.write_text(json.dumps([{"date": "2026-01-01"}]), encoding="utf-8")
    monkeypatch.setattr(cli_mod, "TRACKING_PATH", log)
    profile_path, posting_path = _write_profile_and_posting(tmp_path)
    rc = main(["track", str(posting_path), "--profile", str(profile_path)])
    assert rc == 0
    entries = json.loads(log.read_text(encoding="utf-8"))
    assert len(entries) == 2


def test_parser_has_track_subcommand():
    from applymap.cli import build_parser

    parser = build_parser()
    subparsers = parser._subparsers._group_actions[0]
    assert "track" in subparsers.choices
    assert callable(subparsers.choices["track"].get_default("func"))


def _seed_applications_log(tmp_path, monkeypatch):
    import json
    from applymap import cli as cli_mod

    log = tmp_path / "applications.json"
    log.write_text(
        json.dumps(
            [
                {"date": "2026-10-10", "company": "Acme", "role": "Backend Dev",
                 "score": 67, "status": "applied"},
                {"date": "2026-10-12", "company": "Globex", "role": "SDE",
                 "score": 82, "status": "interview"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli_mod, "TRACKING_PATH", log)
    return log


def test_applications_lists_newest_first(tmp_path, monkeypatch, capsys):
    _seed_applications_log(tmp_path, monkeypatch)
    rc = main(["applications"])
    assert rc == 0
    lines = [l for l in capsys.readouterr().out.splitlines() if "/100" in l]
    assert len(lines) == 2
    assert "Globex" in lines[0]  # newest first
    assert "Acme" in lines[1]


def test_applications_filters_by_status(tmp_path, monkeypatch, capsys):
    _seed_applications_log(tmp_path, monkeypatch)
    rc = main(["applications", "--status", "interview"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Globex" in out
    assert "Acme" not in out
    assert "1 application(s) tracked." in out


def test_applications_empty_log_message(tmp_path, monkeypatch, capsys):
    _seed_applications_log(tmp_path, monkeypatch).unlink()
    rc = main(["applications"])
    assert rc == 0
    assert "No applications tracked yet" in capsys.readouterr().out


def test_applications_corrupted_log_is_friendly_error(tmp_path, monkeypatch, capsys):
    from applymap import cli as cli_mod

    log = tmp_path / "applications.json"
    log.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(cli_mod, "TRACKING_PATH", log)
    rc = main(["applications"])
    assert rc == 1
    assert "not valid JSON" in capsys.readouterr().err


def test_applications_non_list_log_is_friendly_error(tmp_path, monkeypatch, capsys):
    from applymap import cli as cli_mod

    log = tmp_path / "applications.json"
    log.write_text('{"oops": "not a list"}', encoding="utf-8")
    monkeypatch.setattr(cli_mod, "TRACKING_PATH", log)
    rc = main(["applications"])
    assert rc == 1
    assert "should be a JSON list" in capsys.readouterr().err


def test_track_corrupted_log_is_friendly_error(tmp_path, monkeypatch, capsys):
    from applymap import cli as cli_mod

    log = tmp_path / "applications.json"
    log.write_text("{corrupted", encoding="utf-8")
    monkeypatch.setattr(cli_mod, "TRACKING_PATH", log)
    profile_path, posting_path = _write_profile_and_posting(tmp_path)
    rc = main(["track", str(posting_path), "--profile", str(profile_path)])
    assert rc == 1
    assert "not valid JSON" in capsys.readouterr().err


def test_analyze_missing_posting_is_friendly_error(tmp_path, capsys):
    profile_path, _ = _write_profile_and_posting(tmp_path)
    rc = main(
        ["analyze", str(tmp_path / "missing.txt"),
         "--profile", str(profile_path)]
    )
    assert rc == 1
    assert "Posting file not found" in capsys.readouterr().err


def test_track_stores_absolute_posting_path(tmp_path, monkeypatch):
    import json
    from applymap import cli as cli_mod

    monkeypatch.setattr(cli_mod, "TRACKING_PATH", tmp_path / "applications.json")
    profile_path, posting_path = _write_profile_and_posting(tmp_path)
    assert main(["track", str(posting_path), "--profile", str(profile_path)]) == 0
    record = json.loads((tmp_path / "applications.json").read_text(encoding="utf-8"))[0]
    assert record["posting"] == str(posting_path.resolve())


def test_track_duplicate_is_skipped(tmp_path, monkeypatch, capsys):
    import json
    from applymap import cli as cli_mod

    monkeypatch.setattr(cli_mod, "TRACKING_PATH", tmp_path / "applications.json")
    profile_path, posting_path = _write_profile_and_posting(tmp_path)
    argv = ["track", str(posting_path), "--profile", str(profile_path),
            "--company", "Acme", "--role", "Backend Dev"]
    assert main(argv) == 0
    capsys.readouterr()
    assert main(argv) == 0
    assert "Already tracking" in capsys.readouterr().out
    entries = json.loads((tmp_path / "applications.json").read_text(encoding="utf-8"))
    assert len(entries) == 1


def test_analyze_json_output(tmp_path, capsys):
    import json

    profile_path, posting_path = _write_profile_and_posting(tmp_path)
    rc = main(["analyze", str(posting_path), "--profile", str(profile_path), "--json"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["score"] == 67
    assert "python" in report["matched"]
    assert "kubernetes" in report["missing"]


def test_read_posting_expands_home(tmp_path, monkeypatch):
    from applymap.cli import _read_posting

    monkeypatch.setenv("HOME", str(tmp_path))
    posting = tmp_path / "posting.txt"
    posting.write_text("Python developer", encoding="utf-8")
    assert _read_posting("~/posting.txt") == "Python developer"


def test_cover_letter_output_creates_parent_dirs(tmp_path, monkeypatch, capsys):
    from applymap import cli as cli_mod

    monkeypatch.setenv("APPLYMAP_API_KEY", "test-key")
    monkeypatch.setattr(
        cli_mod, "draft_cover_letter", lambda prof, posting, company, role: "Dear Acme"
    )
    profile_path, posting_path = _write_profile_and_posting(tmp_path)
    out = tmp_path / "letters" / "acme.md"
    rc = main(
        [
            "cover-letter",
            str(posting_path),
            "--company", "Acme",
            "--role", "Backend Dev",
            "--profile", str(profile_path),
            "--output", str(out),
        ]
    )
    assert rc == 0
    assert out.read_text(encoding="utf-8") == "Dear Acme\n"
    assert "Wrote cover letter" in capsys.readouterr().out


def test_track_duplicate_ignores_case_and_whitespace(tmp_path, monkeypatch, capsys):
    import json
    from applymap import cli as cli_mod

    monkeypatch.setattr(cli_mod, "TRACKING_PATH", tmp_path / "applications.json")
    profile_path, posting_path = _write_profile_and_posting(tmp_path)
    base = ["track", str(posting_path), "--profile", str(profile_path)]
    assert main(base + ["--company", "Acme", "--role", "Backend Dev"]) == 0
    capsys.readouterr()
    # Same application with different casing/whitespace must not double-log.
    assert main(base + ["--company", "  acme ", "--role", "BACKEND dev"]) == 0
    assert "Already tracking" in capsys.readouterr().out
    entries = json.loads((tmp_path / "applications.json").read_text(encoding="utf-8"))
    assert len(entries) == 1


def test_analyze_ai_skips_api_call_when_nothing_missing(tmp_path, capsys, monkeypatch):
    import yaml
    from applymap import cli as cli_mod

    monkeypatch.setenv("APPLYMAP_API_KEY", "test-key")
    called = []
    monkeypatch.setattr(
        cli_mod, "summarize_gaps",
        lambda prof, missing: called.append(missing) or "summary",
    )
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        yaml.safe_dump({"name": "T", "skills": ["python", "sql"]}), encoding="utf-8"
    )
    posting_path = tmp_path / "posting.txt"
    posting_path.write_text("Python and SQL developer.", encoding="utf-8")
    rc = main(["analyze", str(posting_path), "--profile", str(profile_path), "--ai"])
    assert rc == 0
    assert called == []  # no paid API call when there is nothing to analyze
    assert "No missing skills" in capsys.readouterr().out


def test_analyze_shows_mention_counts(tmp_path, capsys):
    profile_path, posting_path = _write_profile_and_posting(tmp_path)
    posting_path.write_text(
        "Backend developer: Python, Python, SQL, and Kubernetes, Kubernetes, "
        "Kubernetes experience required.",
        encoding="utf-8",
    )
    rc = main(["analyze", str(posting_path), "--profile", str(profile_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "python (mentioned 2x)" in out
    assert "kubernetes (mentioned 3x)" in out


def test_analyze_json_includes_mentions(tmp_path, capsys):
    import json

    profile_path, posting_path = _write_profile_and_posting(tmp_path)
    rc = main(["analyze", str(posting_path), "--profile", str(profile_path), "--json"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mentions"]["python"] == 1
    assert report["mentions"]["kubernetes"] == 1


def test_rank_min_score_hides_low_fit(tmp_path, capsys):
    profile_path, _ = _write_profile_and_posting(tmp_path)
    good = tmp_path / "good.txt"
    good.write_text("Python and SQL developer.", encoding="utf-8")
    bad = tmp_path / "bad.txt"
    bad.write_text("Rust and Kubernetes engineer.", encoding="utf-8")
    rc = main(["rank", str(good), str(bad), "--profile", str(profile_path),
               "--min-score", "50"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "good" in out
    assert "bad" not in out.split("hidden")[0]
    assert "1 posting(s) below --min-score 50 hidden" in out


def test_rank_min_score_filters_csv(tmp_path):
    import csv

    profile_path, _ = _write_profile_and_posting(tmp_path)
    good = tmp_path / "good.txt"
    good.write_text("Python and SQL developer.", encoding="utf-8")
    bad = tmp_path / "bad.txt"
    bad.write_text("Rust and Kubernetes engineer.", encoding="utf-8")
    csv_path = tmp_path / "rank.csv"
    rc = main(["rank", str(good), str(bad), "--profile", str(profile_path),
               "--csv", str(csv_path), "--min-score", "50"])
    assert rc == 0
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["label"] for r in rows] == ["good"]


def test_rank_min_score_rejects_out_of_range(capsys):
    with __import__("pytest").raises(SystemExit) as exc:
        main(["rank", "x.txt", "--min-score", "101"])
    assert exc.value.code == 2
    assert "between 0 and 100" in capsys.readouterr().err


def test_rank_csv_expands_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    profile_path, _ = _write_profile_and_posting(tmp_path)
    good = tmp_path / "good.txt"
    good.write_text("Python and SQL developer.", encoding="utf-8")
    rc = main(["rank", str(good), "--profile", str(profile_path),
               "--csv", "~/reports/rank.csv"])
    assert rc == 0
    assert (tmp_path / "reports" / "rank.csv").exists()
    assert not (tmp_path / "~").exists()


def test_cover_letter_output_expands_home(tmp_path, monkeypatch):
    from applymap import cli as cli_mod

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("APPLYMAP_API_KEY", "test-key")
    monkeypatch.setattr(
        cli_mod, "draft_cover_letter", lambda prof, posting, company, role: "Dear Acme"
    )
    profile_path, posting_path = _write_profile_and_posting(tmp_path)
    rc = main(
        [
            "cover-letter", str(posting_path),
            "--company", "Acme", "--role", "Backend Dev",
            "--profile", str(profile_path),
            "--output", "~/letters/acme.md",
        ]
    )
    assert rc == 0
    assert (tmp_path / "letters" / "acme.md").read_text(encoding="utf-8") == "Dear Acme\n"
    assert not (tmp_path / "~").exists()


def _write_sparse_profile(tmp_path, **overrides):
    import yaml

    data = {"name": "", "headline": "", "skills": [],
            "experience": [], "target_roles": []}
    data.update(overrides)
    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_check_profile_clean_passes(tmp_path, capsys):
    import yaml

    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        yaml.safe_dump(
            {
                "name": "Test Dev",
                "headline": "Software engineering student",
                "skills": ["python", "sql", "docker"],
                "experience": ["automated deployments"],
                "target_roles": ["Backend Developer"],
            }
        ),
        encoding="utf-8",
    )
    rc = main(["check-profile", "--profile", str(profile_path)])
    assert rc == 0
    assert "Profile looks good." in capsys.readouterr().out


def test_check_profile_reports_gaps(tmp_path, capsys):
    profile_path = _write_sparse_profile(tmp_path)
    rc = main(["check-profile", "--profile", str(profile_path)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "Profile issues found:" in out
    assert "name is empty" in out
    assert "no skills listed" in out
    assert "no target_roles" in out
    assert "no experience entries" in out


def test_check_profile_warns_on_unknown_skills(tmp_path, capsys):
    profile_path = _write_sparse_profile(
        tmp_path, name="T", headline="h", skills=["python", "cobol"],
        experience=["x"], target_roles=["Backend Dev"],
    )
    rc = main(["check-profile", "--profile", str(profile_path)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "cobol" in out
    assert "matcher's vocabulary" in out


def test_check_profile_missing_file_is_friendly_error(tmp_path, capsys):
    rc = main(["check-profile", "--profile", str(tmp_path / "nope.yaml")])
    assert rc == 1
    assert "Profile not found" in capsys.readouterr().err


def test_parser_has_check_profile_subcommand():
    parser = build_parser()
    subparsers = parser._subparsers._group_actions[0]
    assert "check-profile" in subparsers.choices
    assert callable(subparsers.choices["check-profile"].get_default("func"))


def test_applications_json_output(tmp_path, monkeypatch, capsys):
    import json

    _seed_applications_log(tmp_path, monkeypatch)
    rc = main(["applications", "--json"])
    assert rc == 0
    entries = json.loads(capsys.readouterr().out)
    assert len(entries) == 2
    assert entries[0]["company"] == "Acme"


def test_applications_json_respects_status_filter(tmp_path, monkeypatch, capsys):
    import json

    _seed_applications_log(tmp_path, monkeypatch)
    rc = main(["applications", "--json", "--status", "interview"])
    assert rc == 0
    entries = json.loads(capsys.readouterr().out)
    assert len(entries) == 1
    assert entries[0]["company"] == "Globex"


def test_parser_has_update_status_subcommand():
    parser = build_parser()
    subparsers = parser._subparsers._group_actions[0]
    assert "update-status" in subparsers.choices
    assert callable(subparsers.choices["update-status"].get_default("func"))


def test_update_status_changes_record(tmp_path, monkeypatch, capsys):
    import json

    log = _seed_applications_log(tmp_path, monkeypatch)
    rc = main(["update-status", "--company", "Acme", "--role", "Backend Dev",
               "--status", "interview"])
    assert rc == 0
    entries = json.loads(log.read_text(encoding="utf-8"))
    acme = [e for e in entries if e["company"] == "Acme"][0]
    assert acme["status"] == "interview"
    assert "Updated Acme" in capsys.readouterr().out


def test_update_status_matches_case_insensitively(tmp_path, monkeypatch):
    import json

    log = _seed_applications_log(tmp_path, monkeypatch)
    rc = main(["update-status", "--company", "  ACME ", "--role", "backend dev",
               "--status", "rejected"])
    assert rc == 0
    entries = json.loads(log.read_text(encoding="utf-8"))
    assert [e for e in entries if e["company"] == "Acme"][0]["status"] == "rejected"


def test_update_status_not_found_is_friendly_error(tmp_path, monkeypatch, capsys):
    _seed_applications_log(tmp_path, monkeypatch)
    rc = main(["update-status", "--company", "Nope", "--role", "Dev",
               "--status", "offer"])
    assert rc == 1
    assert "No tracked application" in capsys.readouterr().out


def test_update_status_ambiguous_match_lists_candidates(tmp_path, monkeypatch, capsys):
    import json
    from applymap import cli as cli_mod

    log = tmp_path / "applications.json"
    log.write_text(
        json.dumps(
            [
                {"date": "2026-10-10", "company": "Acme", "role": "Backend Dev",
                 "score": 67, "status": "applied"},
                {"date": "2026-10-11", "company": "Acme", "role": "Backend Dev",
                 "score": 50, "status": "applied"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli_mod, "TRACKING_PATH", log)
    rc = main(["update-status", "--company", "Acme", "--role", "Backend Dev",
               "--status", "interview"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "Multiple applications" in out
    # Neither record is changed when the match is ambiguous.
    entries = json.loads(log.read_text(encoding="utf-8"))
    assert all(e["status"] == "applied" for e in entries)


def test_applications_json_empty_log(tmp_path, monkeypatch, capsys):
    import json

    _seed_applications_log(tmp_path, monkeypatch).unlink()
    rc = main(["applications", "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == []
