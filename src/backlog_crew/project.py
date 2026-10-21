"""Per-repository configuration: `.backlog-crew.yaml` at the target repo's root.

The template with every field explained is templates/backlog-crew.yaml.
"""

import shlex
from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_FILE = ".backlog-crew.yaml"
DEFAULT_SPEC = "docs/product-spec.md"
DEFAULT_MAX_ISSUES = 5


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Area:
    name: str
    path: str
    description: str
    test: str
    rules: str


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    description: str
    spec: str
    areas: dict[str, Area]
    integration_checks: list[tuple[str, ...]]
    review_rules: str
    max_issues: int

    @classmethod
    def load(cls, repo_root: Path) -> "ProjectConfig":
        path = repo_root / CONFIG_FILE
        if not path.is_file():
            raise ConfigError(f"{CONFIG_FILE} not found at the repository root")
        try:
            raw = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"{CONFIG_FILE} is not valid YAML: {e}") from e
        return cls.parse(raw, repo_root)

    @classmethod
    def parse(cls, raw: dict, repo_root: Path) -> "ProjectConfig":
        project = raw.get("project") or {}
        if not project.get("name"):
            raise ConfigError("project.name is required")

        areas: dict[str, Area] = {}
        for name, a in (raw.get("areas") or {}).items():
            a = a or {}
            area_path = str(a.get("path", "")).strip().rstrip("/") or "."
            resolved = (repo_root / area_path).resolve()
            if not resolved.is_relative_to(repo_root.resolve()):
                raise ConfigError(f"areas.{name}.path must be inside the repository")
            if not resolved.is_dir():
                raise ConfigError(f"areas.{name}.path '{area_path}' does not exist")
            areas[name] = Area(
                name=name,
                path=area_path,
                description=str(a.get("description", "")).strip(),
                test=str(a.get("test", "")).strip(),
                rules=str(a.get("rules", "")).strip(),
            )
        if not areas:
            raise ConfigError("define at least one entry under areas")

        checks = [tuple(pair) for pair in raw.get("integration_checks") or []]
        for pair in checks:
            unknown = [n for n in pair if n not in areas]
            if len(pair) < 2 or unknown:
                raise ConfigError(
                    f"integration_checks entry {list(pair)} must name 2+ defined areas"
                )

        return cls(
            name=str(project["name"]).strip(),
            description=str(project.get("description", "")).strip(),
            spec=str(raw.get("spec") or DEFAULT_SPEC),
            areas=areas,
            integration_checks=checks,
            review_rules=str((raw.get("review") or {}).get("rules", "")).strip(),
            max_issues=int((raw.get("planner") or {}).get("max_issues", DEFAULT_MAX_ISSUES)),
        )

    def command_names(self) -> set[str]:
        """First word of each area's test command, so agents may run them."""
        return {shlex.split(a.test)[0] for a in self.areas.values() if a.test}

    def context(self) -> str:
        """Project description for system prompts."""
        lines = [f"Project: {self.name}"]
        if self.description:
            lines += ["", self.description]
        lines += ["", "Areas of the repository:"]
        for a in self.areas.values():
            test = f" (tests: `{a.test}`)" if a.test else ""
            lines.append(f"- {a.name}: {a.path}/ {a.description}{test}".rstrip())
        lines += ["", f"Product spec: {self.spec}"]
        return "\n".join(lines)
