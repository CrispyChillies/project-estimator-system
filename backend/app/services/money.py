"""Money helpers. Canonical storage is whole VND; USD is a display/input conversion at the workspace rate.

Never convert twice: convert at the edge (input -> VND once, VND -> display once)."""

from __future__ import annotations

import re
from dataclasses import dataclass

CURRENCIES = ("VND", "USD")
VND_STEP = 1000  # inputs are rounded to the nearest 1.000 VND


def usd_to_vnd(usd: float, rate: float, *, step: int = VND_STEP) -> int:
    """USD -> whole VND, rounded to `step` (default 1.000 ₫)."""
    return int(round(usd * rate / step)) * step


def vnd_to_usd(vnd: float, rate: float) -> float:
    return vnd / rate


def to_vnd(amount: float, currency: str, rate: float, *, step: int = VND_STEP) -> int:
    cur = currency.upper()
    if cur == "VND":
        return int(round(amount / step)) * step
    if cur == "USD":
        return usd_to_vnd(amount, rate, step=step)
    raise ValueError(f"unsupported currency {currency!r}")


def from_vnd(vnd: float, currency: str, rate: float) -> float:
    cur = currency.upper()
    if cur == "VND":
        return float(vnd)
    if cur == "USD":
        return vnd_to_usd(vnd, rate)
    raise ValueError(f"unsupported currency {currency!r}")


def format_money(vnd: float, currency: str, rate: float) -> str:
    """Plain-text rendering for exports and agent messages (vi-VN style for VND, en-US for USD)."""
    if currency.upper() == "USD":
        return f"${vnd_to_usd(vnd, rate):,.2f}"
    return f"{int(round(vnd)):,}".replace(",", ".") + " ₫"


# ---------------------------------------------------------------- parsing free text ("300tr", "1,5 tỷ", "$5,000")

@dataclass(frozen=True)
class Money:
    amount: float  # in `currency` units (not yet VND)
    currency: str  # VND | USD

    def vnd(self, rate: float) -> int:
        return to_vnd(self.amount, self.currency, rate)


_MULT = {
    "ty": 1e9, "tỷ": 1e9, "tỉ": 1e9, "ti": 1e9, "billion": 1e9, "b": 1e9,
    "tr": 1e6, "triệu": 1e6, "trieu": 1e6, "million": 1e6, "m": 1e6, "mil": 1e6,
    "nghìn": 1e3, "nghin": 1e3, "ngàn": 1e3, "ngan": 1e3, "k": 1e3, "thousand": 1e3,
}
_VN_ONLY = {"ty", "tỷ", "tỉ", "ti", "tr", "triệu", "trieu", "nghìn", "nghin", "ngàn", "ngan"}  # Vietnamese words mean VND
_VND_WORDS = r"(?:₫|đ|vnd|vnđ|dong|đồng|dồng)"
_USD_WORDS = r"(?:\$|usd|us\$|dollars?|đô|do la|đô la)"
_MULT_RE = "|".join(sorted((re.escape(k) for k in _MULT), key=len, reverse=True))
_NUM = r"\d[\d.,]*"
_PATTERN = re.compile(
    rf"(?P<pre>\$|us\$)?\s*(?P<num>{_NUM})\s*(?P<mult>(?:{_MULT_RE})(?!\w))?\s*(?P<unit>{_VND_WORDS}|{_USD_WORDS})?",
    re.IGNORECASE,
)


def _to_float(num: str, *, has_multiplier: bool, currency_hint: str) -> float | None:
    """Disambiguate separators. With a multiplier word ("1,5 tỷ", "1.5 tỷ") a single separator is decimal.
    Without one, groups of exactly three digits are thousands separators ("1.250.000", "$5,000")."""
    num = num.strip(".,")
    if not num:
        return None
    seps = [c for c in num if c in ".,"]
    if not seps:
        return float(num)
    if len(set(seps)) == 2:  # e.g. 1.234,56 or 1,234.56: the last one is the decimal separator
        dec = num[max(num.rfind("."), num.rfind(","))]
        thou = "," if dec == "." else "."
        return float(num.replace(thou, "").replace(dec, "."))
    sep = seps[0]
    parts = num.split(sep)
    if len(seps) > 1:  # repeated same separator -> thousands
        return float("".join(parts)) if all(len(p) == 3 for p in parts[1:]) else None
    head, tail = parts
    if has_multiplier:
        return float(f"{head}.{tail}")
    if len(tail) == 3 and head:
        return float(head + tail)  # 5,000 / 5.000 -> thousands
    return float(f"{head}.{tail}")


def parse_money(text: str, *, default_currency: str = "VND") -> Money | None:
    """First money amount in `text` or None. Understands Vietnamese and English:
    '300tr', '300 triệu', '1,5 tỷ', '1.5 tỷ', '50k', '$5,000', '5000 USD', '200.000.000đ'.
    A bare number or 'k'/'m' suffix without a currency uses `default_currency`."""
    best: Money | None = None
    for m in _PATTERN.finditer(text):
        raw = m.group("num")
        mult_word = (m.group("mult") or "").lower()
        unit = (m.group("unit") or "").lower()
        pre = (m.group("pre") or "").lower()
        # 'm'/'b' alone next to a plain number is too ambiguous (minutes, meters): require a currency cue
        if mult_word in ("m", "b", "mil") and not (unit or pre):
            continue
        cur = default_currency.upper()
        if pre or re.fullmatch(_USD_WORDS, unit or "x", re.IGNORECASE):
            cur = "USD"
        elif (unit and re.fullmatch(_VND_WORDS, unit, re.IGNORECASE)) or mult_word in _VN_ONLY:
            cur = "VND"
        value = _to_float(raw, has_multiplier=bool(mult_word), currency_hint=cur)
        if value is None:
            continue
        value *= _MULT.get(mult_word, 1.0)
        if value <= 0:
            continue
        if not (mult_word or unit or pre) and value < 1000:
            continue  # a bare small number is not a budget
        cand = Money(value, cur)
        # prefer a figure that carries an explicit cue (multiplier or currency) over a bare number
        if mult_word or unit or pre:
            return cand
        best = best or cand
    return best
