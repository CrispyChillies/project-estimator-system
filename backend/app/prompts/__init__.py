from pathlib import Path
from string import Template

PROMPT_DIR = Path(__file__).parent

PROMPT_VERSIONS = {
    "extraction": "extraction-v1",
    "decomposition": "decomposition-v1",
    "estimation": "estimation-v1",
    "lessons": "lessons-v1",
    "chat_agent": "chat-agent-v2",
    "agent_panel": "agent-panel-v1",
}

UNIT_DEFINITION = (
    "Unit: hours of work by ONE competent mid-level engineer of the given role, including implementation, "
    "self-testing and code review, excluding project-management overhead unless the task itself is a PM task."
)


def render(name: str, **values: object) -> str:
    text = (PROMPT_DIR / f"{name}.md").read_text()
    return Template(text).safe_substitute(unit=UNIT_DEFINITION, **{k: str(v) for k, v in values.items()})
