from pathlib import Path

import pytest
import yaml

from backlog_crew.project import CONFIG_FILE, ConfigError, ProjectConfig

TEMPLATE = Path(__file__).parents[1] / "templates" / "backlog-crew.yaml"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "api").mkdir()
    (tmp_path / "web").mkdir()
    return tmp_path


def test_template_is_valid(repo: Path):
    (repo / CONFIG_FILE).write_text(TEMPLATE.read_text())
    config = ProjectConfig.load(repo)
    assert set(config.areas) == {"api", "web"}
    assert config.command_names() == {"npm", "npx"}
    assert config.integration_checks == [("api", "web")]
    assert "api: api/" in config.context()


def test_missing_file(repo: Path):
    with pytest.raises(ConfigError, match="not found"):
        ProjectConfig.load(repo)


@pytest.mark.parametrize(
    "raw, message",
    [
        ({"areas": {"api": {"path": "api"}}}, "project.name"),
        ({"project": {"name": "x"}}, "at least one"),
        ({"project": {"name": "x"}, "areas": {"a": {"path": "nope"}}}, "does not exist"),
        ({"project": {"name": "x"}, "areas": {"a": {"path": "../"}}}, "inside the repository"),
        (
            {
                "project": {"name": "x"},
                "areas": {"api": {"path": "api"}},
                "integration_checks": [["api", "mobile"]],
            },
            "2\\+ defined areas",
        ),
    ],
)
def test_invalid_configs(repo: Path, raw: dict, message: str):
    with pytest.raises(ConfigError, match=message):
        ProjectConfig.parse(raw, repo)


def test_single_area_repo(repo: Path):
    config = ProjectConfig.parse({"project": {"name": "x"}, "areas": {"app": {"path": "."}}}, repo)
    assert config.areas["app"].path == "."
    assert config.integration_checks == []


def test_template_yaml_has_no_tabs():
    assert "\t" not in TEMPLATE.read_text()
    yaml.safe_load(TEMPLATE.read_text())
