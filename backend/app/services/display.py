"""Display aliases for the archived test data: the stored rows stay untouched, only what the UI shows is neutral
(e.g. "Synthetic Client A" -> "Client A", "demo_brief_2.md" -> "brief_2.md")."""

import re

_RULES = [(re.compile(r"\bSynthetic Client\b"), "Client"), (re.compile(r"\bdemo[_-](brief)", re.I), r"\1")]


def alias(text: str | None) -> str | None:
    if not text:
        return text
    for rx, rep in _RULES:
        text = rx.sub(rep, text)
    return text
