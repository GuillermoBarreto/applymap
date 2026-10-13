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


