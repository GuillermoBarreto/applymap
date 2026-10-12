from applymap import matcher


def test_extract_required_skills_finds_tokens():
    posting = "We need a Python developer with React, Docker and SQL experience."
    found = matcher.extract_required_skills(posting)
    assert "python" in found
    assert "react" in found
    assert "docker" in found
    assert "sql" in found


def test_extract_required_skills_multiword():
    posting = "Experience with spring boot and machine learning preferred."
    found = matcher.extract_required_skills(posting)
    assert "spring boot" in found
    assert "machine learning" in found


def test_extract_required_skills_empty_posting():
    assert matcher.extract_required_skills("") == []


def test_match_scores_overlap():
    report = matcher.match(["python", "sql"], ["python", "sql", "react"])
    assert report["score"] == 67  # 2 of 3
    assert report["matched"] == ["python", "sql"]
    assert report["missing"] == ["react"]


def test_match_no_requirements_scores_zero():
    report = matcher.match(["python"], [])
    assert report["score"] == 0
    assert report["matched"] == []
    assert report["missing"] == []


def test_match_dedupes_required():
    report = matcher.match(["python"], ["python", "python", "react"])
    assert report["required"] == ["python", "react"]


def test_rank_postings_orders_best_first():
    postings = [
        ("bad-fit", "We need Kubernetes and Rust and Go engineers."),
        ("good-fit", "Python developer with SQL experience."),
    ]
    ranked = matcher.rank_postings(["python", "sql"], postings)
    assert ranked[0]["label"] == "good-fit"
    assert ranked[1]["label"] == "bad-fit"
    assert ranked[0]["score"] > ranked[1]["score"]
