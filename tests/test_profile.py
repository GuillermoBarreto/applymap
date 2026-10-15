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
