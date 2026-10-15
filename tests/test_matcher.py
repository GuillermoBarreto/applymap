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


def test_extract_resolves_aliases():
    found = matcher.extract_required_skills("We run k8s in production with a TS frontend.")
    assert "kubernetes" in found
    assert "typescript" in found
    assert "k8s" not in found
    assert "ts" not in found


def test_extract_alias_dedupes():
    found = matcher.extract_required_skills("Postgres and PostgreSQL required.")
    assert found == ["postgresql"]


def test_match_resolves_aliases_on_both_sides():
    report = matcher.match(["kubernetes", "javascript"], ["k8s", "js", "go"])
    assert report["score"] == 67  # 2 of 3
    assert report["matched"] == ["kubernetes", "javascript"]
    assert report["missing"] == ["go"]


def test_extract_finds_newer_stack_tokens():
    posting = (
        "We need Kafka and Elasticsearch experience. "
        "S3 and Lambda a plus; Vite or Express on the frontend."
    )
    found = matcher.extract_required_skills(posting)
    for skill in ("kafka", "elasticsearch", "s3", "lambda", "vite", "express"):
        assert skill in found


def test_extract_golang_alias_resolves_to_go():
    assert matcher.canonicalize("golang") == "go"
    found = matcher.extract_required_skills("Golang backend developer")
    assert "go" in found
    assert "golang" not in found


def test_canonicalize_unknown_passes_through():
    assert matcher.canonicalize("  Python ") == "python"
    assert matcher.canonicalize("cobol") == "cobol"


def test_extract_ignores_sentence_final_dots():
    found = matcher.extract_required_skills("We need Python, SQL and Docker.")
    assert "python" in found
    assert "sql" in found
    assert "docker" in found


def test_tokenize_keeps_tech_tokens_and_lowercases():
    tokens = matcher.tokenize("Python, Node.js and C++ devs wanted.")
    assert "python" in tokens
    assert "node.js" in tokens
    assert "c++" in tokens
    assert "Python" not in tokens
