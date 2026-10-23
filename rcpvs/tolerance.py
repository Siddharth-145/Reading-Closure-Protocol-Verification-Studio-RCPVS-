"""Typed tolerance constraints (Task 1D, 'stronger scope'): value, unit, comparator, lower/upper bound, inclusivity.

This module evaluates concrete durations against a configured constraint. It does NOT make the FSM verifier a general
numeric/timed verifier: the FSM only sees the boundary as a discrete transition; this module documents and tests the
boundary semantics each reading assumes."""
from __future__ import annotations

UNIT_SECONDS = {"ms": 0.001, "millisecond": 0.001, "milliseconds": 0.001, "s": 1.0, "sec": 1.0, "secs": 1.0, "second": 1.0, "seconds": 1.0,
                "min": 60.0, "minute": 60.0, "minutes": 60.0}
UPPER = {"within", "up to", "at most", "no more than"}
LOWER = {"at least", "no less than"}
ACCEPTED, REJECTED, INVALID, UNRESOLVED = "ACCEPTED", "REJECTED", "INVALID_INPUT", "UNRESOLVED"


def typed_constraint(num: dict, inclusive: bool):
    """num = {'comparator','value','unit'} parsed from text. Returns a typed constraint or None (e.g. 'approximately')."""
    if not num or num["unit"] is None or num["unit"].lower() not in UNIT_SECONDS: return None
    f, v, cmp_ = UNIT_SECONDS[num["unit"].lower()], num["value"] * UNIT_SECONDS[num["unit"].lower()], num["comparator"]
    base = {"comparator": cmp_, "declared_value": num["value"], "declared_unit": num["unit"].lower(), "canonical_unit": "seconds"}
    if cmp_ in UPPER: return dict(base, lower=0.0, lower_inclusive=True, upper=v, upper_inclusive=inclusive)
    if cmp_ in LOWER: return dict(base, lower=v, lower_inclusive=inclusive, upper=None, upper_inclusive=None)
    return None


def evaluate(c, value, unit=None):
    """Decide a concrete value against a typed constraint. Returns (verdict, reason)."""
    if c is None: return UNRESOLVED, "no typed constraint (tolerance unspecified)"
    if value is None: return INVALID, "missing duration"
    if not isinstance(value, (int, float)) or isinstance(value, bool): return INVALID, "duration is not a number"
    u = (unit or c["canonical_unit"]).lower()
    if u not in UNIT_SECONDS: return REJECTED, f"wrong or unsupported unit '{unit}'"
    s = value * UNIT_SECONDS[u]
    note = "" if u == "seconds" else f" (explicitly converted from {u})"
    if s < 0: return INVALID, "negative duration" + note
    lo, hi = c["lower"], c["upper"]
    ok = (s > lo or (c["lower_inclusive"] and abs(s - lo) < 1e-12)) if lo is not None else True
    if ok and hi is not None: ok = s < hi - 1e-12 or (c["upper_inclusive"] and abs(s - hi) < 1e-12)
    return (ACCEPTED if ok else REJECTED), ("within bounds" if ok else "outside bounds") + note


def boundary_table(c):
    """Standard boundary probes for a typed constraint; the expected verdicts follow from the constraint itself."""
    ref = c["upper"] if c["upper"] is not None else c["lower"]
    probes = [("zero", 0, None), ("just below boundary", round(ref - 0.001, 6), None), ("exactly at boundary", ref, None),
              ("just above boundary", round(ref + 0.001, 6), None), ("negative", -1, None), ("missing", None, None), ("wrong unit", 5, "parsecs")]
    return [{"case": n, "value": v, "unit": u, "verdict": evaluate(c, v, u)[0], "reason": evaluate(c, v, u)[1]} for n, v, u in probes]
