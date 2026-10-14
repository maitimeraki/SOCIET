"""Whole-string classifier: is a name a measure value that belongs in a
property, not a node? Deterministic backstop to the extraction prompt, so a
weak analysis model cannot leak "$2.5 billion" as a node.

ponytail: whole-string match only. Known true-positives on names that look like
measures ("3M", "7-Eleven") are accepted for now; add a proper-noun allowlist
when they measurably matter.
"""

import re

_MONEY = re.compile(
    r"^(?:[$€£¥]\s?|(?:usd|eur|gbp|jpy|inr|cad|aud)\s?)?\d[\d,]*(?:\.\d+)?\s*(?:k|m|bn?|billion|million|thousand|trillion)?$",
    re.I,
)
_DATE = re.compile(
    r"^(?:\d{4}(?:-\d{2}(?:-\d{2})?)?|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})$",
    re.I,
)
_PCT = re.compile(r"^\d[\d,]*(?:\.\d+)?\s?%$")
_QTY = re.compile(r"^\d[\d,]*(?:\.\d+)?\s?[a-z]{1,12}$", re.I)

_MAGNITUDE = {
    "k": 1e3,
    "m": 1e6,
    "mn": 1e6,
    "bn": 1e9,
    "b": 1e9,
    "billion": 1e9,
    "million": 1e6,
    "thousand": 1e3,
    "trillion": 1e12,
}
_SYMBOL_CUR = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def is_literal_value(name: str) -> bool:
    s = (name or "").strip()
    if not s:
        return False
    # A capitalized multi-word proper noun ("2024 Paris Olympics") has an
    # internal space the quantity pattern forbids — it is not a pure measure.
    return bool(
        _MONEY.fullmatch(s)
        or _DATE.fullmatch(s)
        or _PCT.fullmatch(s)
        or _QTY.fullmatch(s)
    )


def coerce_value(name: str) -> tuple[str, object]:
    """(value_type, value) for a literal string; ("string", name) if not a literal."""
    s = (name or "").strip()
    if _PCT.fullmatch(s):
        return "percentage", float(s.rstrip("% ").replace(",", ""))
    if _DATE.fullmatch(s):
        return "date", s
    if _MONEY.fullmatch(s):
        return "money", {"amount": _money_amount(s), "currency": _money_currency(s)}
    if _QTY.fullmatch(s):
        return "quantity", {"value": s, "unit": _unit(s)}
    return "string", s


def _money_amount(s: str) -> float:
    m = _NUMBER.search(s)
    if not m:
        return 0.0
    amount = float(m.group().replace(",", ""))
    return amount * _MAGNITUDE.get(s[m.end() :].strip().lower(), 1.0)


def _money_currency(s: str) -> str:
    for symbol, iso in _SYMBOL_CUR.items():
        if symbol in s:
            return iso
    code = re.match(r"(usd|eur|gbp|jpy|inr|cad|aud)", s.strip(), re.I)
    return code.group(1).upper() if code else "USD"


def _unit(s: str) -> str:
    unit = re.search(r"[a-z]+\s*$", s, re.I)
    return unit.group().strip().lower() if unit else ""
