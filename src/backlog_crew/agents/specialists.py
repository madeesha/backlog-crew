"""Specialist agents, exposed to the orchestrator as tools (Strands agents-as-tools).

There is one `developer` tool for every area in `.backlog-crew.yaml`, so the crew adapts to
any repository layout. Each call builds a fresh agent, so specialists don't carry context
between calls; the orchestrator passes what they need in the task text.
"""

from strands import Agent, tool

from backlog_crew.agents import prompts
from backlog_crew.model import make_model
from backlog_crew.project import ProjectConfig
from backlog_crew.tools.workspace import Workspace


def _ask(name: str, system_prompt: str, tools: list, task: str) -> str:
    agent = Agent(
        name=name,
        model=make_model(name),
        system_prompt=system_prompt,
        tools=tools,
        callback_handler=None,
    )
    return str(agent(task))


def specialist_tools(ws: Workspace, project: ProjectConfig) -> list:
    context = project.context()
    read_only = ws.tools()

    @tool
    def developer(area: str, task: str) -> str:
        """Implement a change in one area of the repository. `area` is an area name from the
        project description; `task` carries the issue, acceptance criteria, interface details
        from other areas, and any review findings to fix. Returns a summary, changed
        interfaces, and the test result."""
        a = project.areas.get(area)
        if a is None:
            return f"unknown area '{area}'. Areas: {', '.join(project.areas)}"
        test_instruction = (
            f"Run `{a.test}` in {a.path}/ before you finish and fix what fails."
            if a.test
            else "This area has no test command; check your change by reading it back."
        )
        system_prompt = prompts.DEVELOPER.format(
            area=a.name,
            path=a.path,
            project=context,
            rules=a.rules or "(none beyond the codebase's own conventions)",
            test_instruction=test_instruction,
        )
        return _ask(f"developer_{a.name}", system_prompt, ws.tools(write_scope=a.path), task)

    @tool
    def integration_check(task: str) -> str:
        """Check that connected areas still agree on their interfaces. Read-only. Returns PASS
        or FAIL with mismatches. Pass a short description of what changed in which areas."""
        pairs = "; ".join(" <-> ".join(p) for p in project.integration_checks)
        system_prompt = prompts.INTEGRATION_CHECK.format(areas=pairs, project=context)
        return _ask("integration_check", system_prompt, read_only, task)

    @tool
    def reviewer(task: str) -> str:
        """Review the branch's changes for bugs and security issues. Read-only. Returns APPROVE
        or CHANGES with findings. Pass the issue and what the developers reported."""
        area_rules = "\n".join(f"- {a.name}: {a.rules}" for a in project.areas.values() if a.rules)
        rules = "\n".join(r for r in [project.review_rules, area_rules] if r) or "(none)"
        system_prompt = prompts.REVIEWER.format(project=context, rules=rules)
        return _ask("reviewer", system_prompt, read_only, task)

    tools = [developer, reviewer]
    if project.integration_checks:
        tools.append(integration_check)
    return tools
