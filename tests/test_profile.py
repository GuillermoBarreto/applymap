import pytest
import yaml

from applymap import profile as profile_mod


def test_normalize_lowercases_and_dedupes_skills():
    data = {"skills": ["Python", "python", " React "], "name": "Test"}
    norm = profile_mod.normalize(data)
    assert norm["skills"] == ["python", "react"]


def test_normalize_defaults():
    norm = profile_mod.normalize({})
    assert norm["skills"] == []
    assert norm["experience"] == []
    assert norm["target_roles"] == []


def test_load_profile_reads_yaml(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        yaml.safe_dump({"name": "Sam", "skills": ["python"], "experience": ["built x"]}),
        encoding="utf-8",
    )
    prof = profile_mod.load_profile(path)
    assert prof["name"] == "Sam"
    assert prof["skills"] == ["python"]


def test_load_profile_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        profile_mod.load_profile(tmp_path / "nope.yaml")


def test_normalize_coerces_non_string_skills():
    norm = profile_mod.normalize({"skills": ["Python", 123, None, "   ", ""]})
    assert norm["skills"] == ["python", "123"]


def test_load_profile_malformed_yaml_raises_friendly_error(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text("name: [unclosed\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="not valid YAML"):
        profile_mod.load_profile(path)


def test_load_profile_rejects_non_mapping_yaml(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="must be a YAML mapping"):
        profile_mod.load_profile(path)


def test_normalize_coerces_bare_string_list_fields():
    from applymap.profile import normalize

    # A bare `skills: python` in YAML parses as a string, not a list —
    # normalize must not explode it into single characters.
    p = normalize({"skills": "Python", "experience": "did things"})
    assert p["skills"] == ["python"]
    assert p["experience"] == ["did things"]


def test_normalize_treats_null_fields_as_empty():
    # A bare `experience:` key in hand-edited YAML parses as None — it must
    # not become ["None"] (which would leak "- None" into cover letters).
    p = profile_mod.normalize({"skills": None, "experience": None,
                               "target_roles": None, "name": None})
    assert p["skills"] == []
    assert p["experience"] == []
    assert p["target_roles"] == []


def test_normalize_still_wraps_bare_scalar_values():
    # Regression guard: the None fix must not break scalar wrapping.
    p = profile_mod.normalize({"skills": "Python", "experience": "did things"})
    assert p["skills"] == ["python"]
    assert p["experience"] == ["did things"]
