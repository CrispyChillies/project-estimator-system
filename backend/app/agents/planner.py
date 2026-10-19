"""Deterministic offline planner: maps the supported phrasings and slash commands to the SAME tool calls a live
model would make, so fake/replay mode (and slash commands in any mode) behave identically and offline demos work.
It is a generator: it yields after every tool call so the runtime can stream events, and returns the reply."""

from __future__ import annotations

import re
from collections.abc import Generator

from app.agents import templates as T
from app.agents.toolkit import ROLE_ALIASES, Toolkit

NUM = r"(\d+(?:\.\d+)?)"
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10}
VAGUE = re.compile(r"\b(better|cheaper|optimi[sz]e|improve|smaller|faster|fix it|clean ?up)\b")

HELP = ("I can change the estimate directly. Try: \"Fit the whole estimate to 400 hours\", \"Make backend about 40% "
        "of the total\", \"Hide Phase 1\", \"Round everything to half hours\", \"Tighten the 3 widest ranges\", "
        "\"Add an SSO task under Authentication with 12–20 hours\", or /fit 400, /adjust +10% backend, /round, "
        "/similar, /remember <fact>.")

Plan = Generator[None, None, str]


def _say(res: dict) -> str:
    if not res.get("ok"):
        return res.get("message", "That did not work.")
    st = res.get("status")
    if st == "awaiting_confirmation":
        return f"Proposed: {res['summary']}. Waiting for your confirmation ({'; '.join(res['reasons'])})."
    if st == "applied":
        b, a = res["before"], res["after"]
        return f"Done: {res['summary']}. Total {b[0]:g}–{b[1]:g} h → {a[0]:g}–{a[1]:g} h."
    return res.get("summary", "")


_MONEY_CUE = re.compile(r"\d\s*(?:tr|triệu|trieu|tỷ|tỉ|ty|k|nghìn|ngàn)\b|\$|usd|vnd|vnđ|₫|đồng|\dđ")
_BUDGET_WORD = re.compile(r"ngân sách|ngan sach|budget|fit|giảm|reduce|xuống|trong vòng|within|under|tối đa|cap\b|"
                          r"bớt|cắt")


def _money_budget(kit: Toolkit, clause: str):
    """A money budget in the clause ("ngân sách 200 triệu", "fit to $8,000") or None. Needs a currency/unit cue."""
    from app.db.models import User
    from app.services.money import parse_money

    if not _BUDGET_WORD.search(clause) or not _MONEY_CUE.search(clause):
        return None
    user = kit.db.get(User, kit.ctx.user_id) if kit.ctx.user_id else None
    return parse_money(clause, default_currency=(user.display_currency if user else "VND") or "VND")


def plan(kit: Toolkit, text: str) -> Plan:
    t = text.strip()
    low = t.lower()
    out: list[str] = []

    def call(name: str, **args):
        res = kit.call(name, args)
        out.append(_say(res))
        return res

    # ---- slash commands ----
    if low.startswith("/"):
        cmd, _, rest = low[1:].partition(" ")
        rest_raw = t[len(cmd) + 1:].strip()
        mny = _money_budget(kit, rest) if cmd in ("fit", "budget") else None
        if mny is None and cmd in ("fit", "budget") and rest and _MONEY_CUE.search(rest):
            from app.services.money import parse_money

            mny = parse_money(rest, default_currency="VND")
        if cmd in ("fit", "budget") and mny is not None:
            call("fit_to_cost_budget", target_amount=mny.amount, currency=mny.currency)
        elif cmd == "fit" and re.match(NUM, rest):
            call("fit_to_budget", target_hours=float(re.match(NUM, rest).group(1)))
        elif cmd == "adjust":
            m = re.match(r"([+-]?\d+(?:\.\d+)?)\s*%?\s*(.*)$", rest)
            if not m:
                out.append("Usage: /adjust +10% [role|group]")
            else:
                who = m.group(2).strip()
                role = ROLE_ALIASES.get(who) if who else None
                call("bulk_adjust", percent=float(m.group(1)), role=role, group=None if role or not who else who)
        elif cmd == "round":
            step = float(rest) if re.fullmatch(NUM, rest or "x") else 0.5
            call("bulk_adjust", percent=0, round_to=step)
        elif cmd == "similar":
            res = call("retrieve_similar_projects", k=int(rest) if rest.isdigit() else 3)
            out[-1] = _refs_text(res)
        elif cmd == "remember" and rest_raw:
            call("remember", text=rest_raw)
        elif cmd == "budget" and re.match(NUM, rest):
            call("remember", text=rest, key="budget_hours", value=float(re.match(NUM, rest).group(1)))
        else:
            out.append(HELP)
        yield
        return "\n".join(x for x in out if x)

    sel = kit.ctx.selection
    for clause in [c.strip() for c in re.split(r"\s*(?:;|\n|\bthen\b)\s*", low) if c.strip()]:
        refers_sel = bool(sel) and re.search(r"\b(these|selected|selection|them|those)\b", clause)
        if refers_sel and (m := re.search(NUM + r"\s*%", clause)):
            down = re.search(r"short|small|less|reduc|cut|decreas|lower|trim", clause)
            call("bulk_adjust", tasks=sel, percent=float(m.group(1)) * (-1 if down else 1))
        elif refers_sel and re.search(r"\b(hide|exclude)\b", clause):
            call("toggle_visibility", tasks=sel, visible=False)
        elif refers_sel and re.search(r"\b(delete|remove|drop)\b", clause):
            call("delete_tasks", tasks=sel)
        elif refers_sel and re.search(r"\bround\b", clause):
            call("bulk_adjust", tasks=sel, percent=0, round_to=0.5)
        elif (mny := _money_budget(kit, clause)) is not None:
            call("fit_to_cost_budget", target_amount=mny.amount, currency=mny.currency)
        elif m := re.search(r"\bfit\b(?: the)?(?: (.+?))? to " + NUM + r"\s*(?:h\b|hours?)?", clause):
            scope = (m.group(1) or "").strip()
            group = None if not scope or re.search(r"whole|estimate|everything|all|total", scope) else scope
            call("fit_to_budget", target_hours=float(m.group(2)), group=group)
        elif m := re.search(r"make (\w+) (?:about |around |roughly |~)?" + NUM + r"\s*% of (?:the )?total", clause):
            call("rebalance_roles", role=ROLE_ALIASES.get(m.group(1), m.group(1)), share_pct=float(m.group(2)))
        elif m := re.search(r"\b(hide|exclude|show|include|unhide)\b (?:the )?(.+?)(?: group)?$", clause):
            call("toggle_visibility", group=m.group(2), visible=m.group(1) in ("show", "include", "unhide"))
        elif re.search(r"\bround\b", clause):
            step = 1.0 if re.search(r"whole|full|1 ?h", clause) else 0.5
            call("bulk_adjust", percent=0, round_to=step)
        elif m := re.search(r"tighten (?:the )?(\d+|\w+) widest", clause):
            n = int(m.group(1)) if m.group(1).isdigit() else WORDNUM.get(m.group(1), 3)
            res = kit.call("run_analysis", {"kind": "risks"})
            yield
            items = []
            for d in (res.get("data") or [])[:n]:
                mid, half = (d["min_hours"] + d["max_hours"]) / 2, (d["max_hours"] - d["min_hours"]) / 4
                items.append({"task": d["id"], "min_hours": max(0.5, round((mid - half) * 2) / 2),
                              "max_hours": round((mid + half) * 2) / 2})
            if items:
                call("set_hours", items=items, rationale=f"Tighten the {n} widest ranges by half")
            else:
                out.append("There are no tasks to tighten.")
        elif m := re.search(r"add (?:an? )?(.+?) task (?:under|to|in|into) (?:the )?(.+?)(?: group)? with "
                            + NUM + r"\s*(?:-|–|to)\s*" + NUM, clause):
            title = m.group(1).strip()
            title = title.upper() if len(title) <= 4 else title.capitalize()
            call("create_task", group=m.group(2).strip(), title=title, min_hours=float(m.group(3)),
                 max_hours=float(m.group(4)))
        elif m := re.search(r"(increase|raise|decrease|reduce|cut)\s+(?:the\s+)?(\w+(?:/\w+)?)?\s*(?:tasks?\s+)?"
                            r"(?:hours?\s+)?by\s+" + NUM + r"\s*%", clause):
            pct = float(m.group(3)) * (1 if m.group(1) in ("increase", "raise") else -1)
            word = (m.group(2) or "").strip()
            role = ROLE_ALIASES.get(word)
            cat = word if word in T.CATEGORY_INFO else None
            call("bulk_adjust", percent=pct, role=role, category=cat)
        elif re.search(r"similar (past )?projects", clause):
            out.append(_refs_text(kit.call("retrieve_similar_projects", {"k": 3})))
        elif m := re.search(r"set (?:a |the )?budget(?: of| to)?\s*" + NUM, clause):
            call("remember", text=m.group(1), key="budget_hours", value=float(m.group(1)))
        elif re.search(r"set (?:a |the )?budget", clause):
            call("ask_user", question="What total budget should I hold the estimate to (in hours)?",
                 options=["300 h", "400 h", "500 h"])
        elif re.match(r"(?:remember|note) ", clause):
            m = re.match(r"(?i)(?:remember|note) (?:that )?(.+)$", t)
            call("remember", text=m.group(1) if m else clause)
        elif re.search(r"ambiguit|unclear|open question", clause):
            res = kit.call("run_analysis", {"kind": "ambiguities"})
            qs = (res.get("data") or {}).get("questions", [])
            out.append(res.get("summary", "") + (":\n" + "\n".join(f"- {q['question']} (±{q['delta'][1]:g} h)"
                                                                  for q in qs[:5]) if qs else "."))
        elif re.search(r"analy[sz]e|draft estimate|overview|summary", clause):
            s = kit.call("get_estimate_summary", {})
            yield
            r = kit.call("run_analysis", {"kind": "risks"})
            d = s.get("data") or {}
            out.append(f"{d.get('task_count')} tasks, {d.get('total_min'):g}–{d.get('total_max'):g} h"
                       + (f" (P50 {d['p50']:.0f} h, P80 {d['p80']:.0f} h)" if d.get("p50") else "") + ". "
                       + r.get("summary", ""))
        elif m := re.search(r"(?:delete|remove|drop) (?:the )?(.+?)(?: task)?$", clause):
            call("delete_tasks", tasks=[m.group(1)])
        elif m := re.search(r"(?:explain|why)\s+(?:is\s+)?(?:the\s+)?(.+?)(?:\s+task)?\??$", clause):
            call("explain_task", task=m.group(1))
        elif re.search(r"\blist\b|show tasks", clause):
            res = kit.call("list_tasks", {})
            out.append("\n".join(f"- {r['title']} ({r['min_hours']:g}–{r['max_hours']:g} h)"
                                 for r in (res.get("data") or [])[:40]))
        elif VAGUE.search(clause):
            call("ask_user", question="What should I optimise for?",
                 options=["Fit to a budget", "Tighten the widest ranges", "Remove low-value scope",
                          "Round to half hours"])
        else:
            continue
        yield
        if kit.ctx.paused:
            break
    if not out:
        out.append(HELP)
    return "\n".join(x for x in out if x)


def _refs_text(res: dict) -> str:
    items = res.get("data") or []
    if not items:
        return "No sufficiently similar past projects (I return fewer rather than weak matches)."
    lines = [f"- {r['name']} ({r['status']}): {r['total_min']:g}–{r['total_max']:g} h"
             + (f", actual {r['actual_total']:g} h" if r.get("actual_total") else "")
             + f" · similarity {r['similarity']:.2f}" for r in items]
    return f"{len(items)} similar past project(s):\n" + "\n".join(lines)
