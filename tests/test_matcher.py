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


def test_match_no_requirements_scores_none():
    # A posting with no recognizable skills is not a 0% fit (issue #10):
    # the score is None and the flag says so explicitly.
    report = matcher.match(["python"], [])
    assert report["score"] is None
    assert report["no_requirements"] is True
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


def test_extract_required_skills_finds_hyphenated_tokens():
    posting = (
        "REST-API design, CI-CD pipelines, Open-API specs, "
        "and React-Native apps."
    )
    found = matcher.extract_required_skills(posting)
    assert "rest" in found
    assert "rest-api" not in found
    assert "ci/cd" in found
    assert "openapi" in found
    assert "react-native" in found


def test_extract_hyphenated_spellings_match_profile_skills():
    posting = "Node-JS and Next-JS experience; a machine-learning background is a plus."
    found = matcher.extract_required_skills(posting)
    assert "node" in found
    assert "nextjs" in found
    assert "machine learning" in found
    report = matcher.match(["node", "javascript"], found)
    assert "node" in report["matched"]


def test_skill_mentions_counts_repeated_and_alias_forms():
    posting = (
        "Kubernetes engineer. We run Kubernetes at scale and our k8s "
        "clusters need a Kubernetes-minded SRE."
    )
    mentions = matcher.skill_mentions(posting, ["kubernetes", "python"])
    assert mentions["kubernetes"] == 3  # 2x whole-token "kubernetes" + 1x "k8s"
    assert mentions["python"] == 0


def test_skill_mentions_multiword_counts_substrings():
    posting = "Machine learning team; machine learning is our core product."
    mentions = matcher.skill_mentions(posting, ["machine learning"])
    assert mentions["machine learning"] == 2


def test_skill_mentions_uses_same_rules_as_extractor():
    # "go" reaches the extractor here through the "golang" alias, not
    # through the plain English word — mentions must agree (issue #28):
    # only the alias occurrence counts, the English "go" does not.
    posting = "We go the extra mile for our customers. Golang a plus."
    assert "go" in matcher.extract_required_skills(posting)
    mentions = matcher.skill_mentions(posting, ["go"])
    assert mentions["go"] == 1  # the "golang" alias only


def test_skill_mentions_ignores_plain_english_go_and_rest():
    posting = (
        "Go developer wanted. We go the extra mile, go team go. "
        "REST API design; get some rest after work."
    )
    mentions = matcher.skill_mentions(posting, ["go", "rest"])
    assert mentions["go"] == 1  # only the "Go" token, not the English words
    assert mentions["rest"] == 1  # only "REST", not lowercase "rest"


def test_extract_resolves_fused_js_spellings():
    found = matcher.extract_required_skills(
        "We need a NodeJS developer with ReactJS and VueJS experience."
    )
    assert "node" in found
    assert "react" in found
    assert "vue" in found
    assert "nodejs" not in found
    assert "reactjs" not in found
    assert "vuejs" not in found


def test_skill_mentions_counts_fused_spellings():
    posting = "NodeJS role: NodeJS and Node.js experience with NodeJS stack."
    mentions = matcher.skill_mentions(posting, ["node"])
    assert mentions["node"] == 4  # nodejs x3 + node.js x1


def test_rank_tiebreak_favors_deeper_skill_mentions():
    # Both postings score 100; the one mentioning python more often wins.
    skills = ["python"]
    shallow = "We need python."
    deep = "Python python python! Python everywhere."
    ranked = matcher.rank_postings(skills, [("shallow", shallow), ("deep", deep)])
    assert [r["label"] for r in ranked] == ["deep", "shallow"]
    assert all(r["score"] == 100 for r in ranked)


def test_rank_higher_score_still_beats_mention_depth():
    skills = ["python", "sql"]
    fit = "We need python and sql."  # score 100
    deep_miss = "Kubernetes kubernetes kubernetes! We also want golang."  # score 0
    ranked = matcher.rank_postings(skills, [("deep", deep_miss), ("fit", fit)])
    assert [r["label"] for r in ranked] == ["fit", "deep"]


def test_rank_tiebreak_keeps_report_schema_unchanged():
    # The tie-break must not add new keys to the report dicts beyond
    # mentions, which rank reports now carry like analyze reports do.
    ranked = matcher.rank_postings(["python"], [("a", "python"), ("b", "python python")])
    assert set(ranked[0]) == {"score", "no_requirements", "matched",
                             "missing", "required", "label", "mentions"}


def test_extract_finds_devops_stack_tokens():
    posting = (
        "DevOps engineer: microservices on Kubernetes, websockets APIs, "
        "serverless on AWS. Maven or Gradle builds; Helm charts; "
        "PowerShell and Unix scripting."
    )
    found = matcher.extract_required_skills(posting)
    for skill in (
        "devops", "microservices", "websockets", "serverless",
        "maven", "gradle", "helm", "powershell", "unix",
    ):
        assert skill in found


def test_extract_resolves_restful_and_singular_forms():
    found = matcher.extract_required_skills(
        "RESTful APIs and a microservice architecture."
    )
    assert "rest" in found
    assert "restful" not in found
    assert "microservices" in found
    assert "microservice" not in found


def test_multiword_skills_need_word_boundaries():
    # "spring bootcamp" is not "spring boot" (issue #13); the plain
    # "spring" token still matches as before.
    found = matcher.extract_required_skills(
        "Join our spring bootcamp program to learn Python."
    )
    assert "spring boot" not in found
    assert "spring" in found
    assert "python" in found


def test_multiword_skill_still_matches_standalone():
    found = matcher.extract_required_skills("We need Spring Boot and python.")
    assert "spring boot" in found


def test_skill_mentions_counts_standalone_phrases_only():
    mentions = matcher.skill_mentions(
        "spring bootcamp spring boot spring boot", ["spring boot"]
    )
    assert mentions["spring boot"] == 2


def test_extract_ignores_plain_english_go_and_rest():
    # The words "go"/"rest" in ordinary prose are not skills (issue #6).
    found = matcher.extract_required_skills(
        "We offer a great place to go further and get plenty of rest."
    )
    assert "go" not in found
    assert "rest" not in found


def test_extract_keeps_tech_spellings_of_go_and_rest():
    found = matcher.extract_required_skills(
        "Experience with Go and REST APIs required."
    )
    assert "go" in found
    assert "rest" in found


def test_extract_all_caps_go_counts_as_the_language():
    # Postings often shout the language: "GO developer" is the language,
    # not the English verb (issue #6's gate only allowed "Go" before).
    found = matcher.extract_required_skills(
        "GO developer wanted: goroutines, channels, and strong testing habits."
    )
    assert "go" in found


def test_extract_unambiguous_alias_forms_still_match():
    # golang/restful/rest-api are unambiguous: they don't need the
    # capitalized spelling to count (issue #6).
    found = matcher.extract_required_skills(
        "golang developer; RESTful service design; rest-api experience."
    )
    assert "go" in found
    assert "rest" in found


def test_rank_sorts_no_requirements_postings_last():
    # A posting with no recognizable skills (score None) ranks below even
    # a true 0/100 (issue #10).
    ranked = matcher.rank_postings(
        ["python"],
        [
            ("skill-less", "A great place to work with motivated people."),
            ("zero-fit", "Kubernetes and Rust engineers wanted."),
        ],
    )
    assert [r["label"] for r in ranked] == ["zero-fit", "skill-less"]
    assert ranked[0]["score"] == 0
    assert ranked[1]["score"] is None


def test_match_sets_no_requirements_false_when_skills_exist():
    report = matcher.match(["python"], ["python", "react"])
    assert report["no_requirements"] is False
    assert report["score"] == 50


def test_extract_finds_infra_and_testing_tokens():
    found = matcher.extract_required_skills(
        "Ansible playbooks, nginx reverse proxy, Prometheus and Grafana "
        "dashboards, Cypress end-to-end tests."
    )
    assert {"ansible", "nginx", "prometheus", "grafana", "cypress"} <= set(found)


def test_rank_includes_mention_counts():
    ranked = matcher.rank_postings(["python"], [("a", "python python")])
    assert ranked[0]["mentions"] == {"python": 2}
