"""Agent cassettes: record live LangChain agent turns once, replay them offline in tests.

A cassette is the ordered list of AI messages (text + tool calls) the model produced for one scenario, plus
the task-id -> title map of the estimate it ran against (ids are remapped by title on replay).
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.core.config import get_settings

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def cassette_dir() -> Path:
    return get_settings().fixtures_dir / "agent_cassettes"


class Recorder(BaseCallbackHandler):
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def on_llm_end(self, response, **kwargs):  # noqa: ANN001
        msg = response.generations[0][0].message
        content = msg.content if isinstance(msg.content, str) else "".join(
            b.get("text", "") for b in msg.content if isinstance(b, dict))
        self.messages.append({"content": content,
                              "tool_calls": [{"name": c["name"], "args": c["args"], "id": c.get("id") or uuid.uuid4().hex}
                                             for c in (msg.tool_calls or [])]})


def save(name: str, messages: list[dict], id_titles: dict[str, str], extra: dict | None = None) -> Path:
    p = cassette_dir() / f"{name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"messages": messages, "id_titles": id_titles, **(extra or {})}, indent=1))
    return p


def _remap(obj: Any, mapping: dict[str, str]) -> Any:
    if isinstance(obj, str):
        return UUID_RE.sub(lambda m: mapping.get(m.group(0), m.group(0)), obj)
    if isinstance(obj, list):
        return [_remap(x, mapping) for x in obj]
    if isinstance(obj, dict):
        return {k: _remap(v, mapping) for k, v in obj.items()}
    return obj


class ReplayChatModel(GenericFakeChatModel):
    """Replays recorded AI messages; supports bind_tools so create_agent accepts it."""

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001
        return self


def replay_model(name: str, current_title_to_id: dict[str, str]) -> ReplayChatModel:
    data = json.loads((cassette_dir() / f"{name}.json").read_text())
    mapping = {old: current_title_to_id[title] for old, title in data["id_titles"].items()
               if title in current_title_to_id}
    msgs: Iterator[AIMessage] = iter(
        AIMessage(content=m["content"], tool_calls=[{**c, "args": _remap(c["args"], mapping), "type": "tool_call"}
                                                    for c in m["tool_calls"]])
        for m in data["messages"])
    return ReplayChatModel(messages=msgs, disable_streaming=True)
