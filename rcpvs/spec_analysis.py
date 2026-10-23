"""Feature 1 (reading operators) + Feature 2 (anchoring / provenance), rule set 2.0.0.

Operators: ORDER, REF, DEF, SCOPE, TOL, MODALITY. A reading is generated ONLY when the operator's
preconditions hold. An explicit cue (bound in the model) yields exactly one reading (ANALYSED_SINGLE).
Anything an operator recognises as ambiguity-bearing but cannot resolve -> UNANALYSED (never guessed,
never silently treated as unambiguous). Reading index 0 of every instruction is the baseline reading.

Interpretation policy (exposed in the report): MUST/SHALL enforced; SHOULD and MAY admit enforced/relaxed
(or omitted/implemented) readings unless model.policy.SHOULD == "enforced_only"; MUST NOT -> derived safety property.
"""
from __future__ import annotations
import hashlib, itertools, re
from .models import *
from .tolerance import typed_constraint, UNIT_SECONDS

RULE_SET_VERSION = "2.0.0"
DEFAULT_POLICY = {"MUST": "enforced", "SHOULD": "both_readings", "MAY": "both_readings", "MUST NOT": "derived_safety_property"}
RULES = {
    "ORDER-1": ReadingRule("ORDER-1", "ORDER", RULE_SET_VERSION, "'X and Y' without ordering cue: Y may replace completion of X."),
    "MOD-1": ReadingRule("MOD-1", "MODALITY", RULE_SET_VERSION, "SHOULD/MAY readings, MUST NOT prohibition, explicit MUST cues."),
    "REF-1": ReadingRule("REF-1", "REF", RULE_SET_VERSION, "Referring phrase with >=2 bound antecedents; unbound anaphora -> UNANALYSED."),
    "DEF-1": ReadingRule("DEF-1", "DEF", RULE_SET_VERSION, "Defined term with >=2 behaviourally distinct senses."),
    "SCOPE-1": ReadingRule("SCOPE-1", "SCOPE", RULE_SET_VERSION, "Scope trigger with >=2 candidate scopes affecting distinct transitions."),
    "TOL-1": ReadingRule("TOL-1", "TOL", RULE_SET_VERSION, "within/at least/at most/up to/approximately/may vary with preserved numbers."),
}
MOD_RE = re.compile(r"\b(MUST NOT|MUST|SHALL|SHOULD|MAY)\b")
TAG_RE = re.compile(r"^\s*\[(I-[\w.]+)\]\s*(.+?)\s*$")
ANAPHORA = re.compile(r"\b(it|they|them|that|the previous (?:request|message))\b", re.I)
COND_RE = re.compile(r"\b(if|when|unless|except)\b(.*)$", re.I)
NUM_RE = re.compile(r"\b(within|at least|at most|up to|approximately|about|no more than|no less than)\s+(\d+(?:\.\d+)?)\s*([A-Za-z]+)?", re.I)


def sha256(s: str) -> str: return hashlib.sha256(s.encode()).hexdigest()


def _norm(s): return re.sub(r"\s+", " ", s.strip().lower())


# ---------------------------------------------------------------- Feature 2: anchoring
def anchor(text: str, model: dict) -> list:
    roles = [r.lower() for r in model.get("roles", {})]
    defs = model.get("definitions", {})
    out, pos = [], 0
    for ln, raw in enumerate(text.splitlines(keepends=True), 1):
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            m = TAG_RE.match(raw)
            body = m.group(2) if m else stripped
            iid = m.group(1) if m else "I-H" + sha256(_norm(body))[:6]     # content-hash ID: stable under whitespace/reordering
            c0 = raw.index(body); start = pos + c0
            mod = MOD_RE.search(body)
            cond = COND_RE.search(body)
            after = body[mod.end():] if mod else body
            out.append(InstructionRecord(
                iid, body, ln, start, start + len(body),
                next((r for r in roles if re.search(r"\b" + re.escape(r) + r"\b", body.lower())), None),
                mod.group(1) if mod else None,
                [t for t in defs if re.search(r"\b" + re.escape(t) + r"\b", body, re.I)],
                model.get("errata", {}).get(iid, []), c0 + 1, sha256(body),
                bool(mod and mod.group(1) == "MUST NOT") or bool(re.search(r"\b(not|never)\b", body, re.I)),
                cond.group(0) if cond else None,
                [a.strip(" .") for a in re.split(r"\band\b|,", after) if a.strip(" .")]))
        pos += len(raw)
    return out


# ---------------------------------------------------------------- Feature 1: operators
def _o(i, desc, patch=None, aligned=False, text=None, **kw):
    return dict({"id": i, "desc": desc, "patch": patch or [], "aligned": aligned, "text": text}, **kw)


def _cue(text, rx):
    m = re.search(rx, text, re.I) if rx else None
    return (m.start(), m.end()) if m else None


def _order(ins, b, ctx):
    p = b.get("ORDER")
    if not p: return COV_INAPPLICABLE, "no ORDER binding for this instruction", None, []
    v, role, t = p.get("vars", {}), p.get("role") or ins.role or "implementation", ins.text
    ordered = _o("ordered", "second event only after first completes", aligned=True, edit_type="clarify-event-order",
                 text=f"The {role} MUST complete {v.get('x','the first event')} before {v.get('y_gerund','the second event')}.")
    unordered = _o("unordered", "second event may occur instead of completing the first",
                   [{"op": "bypass", "remove": p["first"], "action": p["second"]}], edit_type="clarify-event-order",
                   text=f"The {role} MAY {v.get('y_verb','perform the second event')} before {v.get('x','the first event')} is completed.")
    if re.search(r"\bMUST\b.*\bbefore\b", t): return COV_SINGLE, "explicit MUST..before cue", [dict(ordered, text=None, cue_span=_cue(t, r"\bbefore\b"))], ["explicit ordering cue"]
    if re.search(r"\bMAY\b.*\bbefore\b.*\bcompleted\b", t): return COV_SINGLE, "explicit MAY..before..completed cue", [dict(unordered, text=None, cue_span=_cue(t, r"\bbefore\b"))], ["explicit relaxed cue"]
    if re.search(r"\b(before|prior to|only after|after completing)\b", t):
        return COV_UNANALYSED, "ordering cue present but not recognised by ORDER-1", None, []
    m = re.search(r"\b(sends?|transmits?)\b.*?\b(and|then)\b.*?\b(clos\w*|terminat\w*)", t, re.I)
    if m:
        return COV_ANALYSED, "conjunction of two events without ordering cue", [dict(ordered, cue_span=(m.start(), m.end())), dict(unordered, cue_span=(m.start(), m.end()))], \
            ["conjunction without ordering cue", "binding gives both events"]
    return COV_INAPPLICABLE, "ORDER trigger not satisfied ('and' alone is not treated as ambiguity)", None, []


def _modality(ins, b, ctx):
    p = b.get("MODALITY")
    if not p: return COV_INAPPLICABLE, "no MODALITY binding for this instruction", None, []
    m, pol = ins.modality, ctx["policy"]
    if m is None: return COV_INAPPLICABLE, "no modality keyword", None, []
    cs = _cue(ins.text, r"\b" + m + r"\b")
    pre = [f"modality={m}", f"policy={pol.get(m)}"] + ([f"conditional: {ins.condition.strip()}"] if ins.condition else []) + (["multi-action sentence: relaxation applies to the bound behaviour only"] if len(ins.actions) > 1 else [])
    if m == "MUST NOT":
        pr = p.get("prohibit")
        if not pr: return COV_UNANALYSED, "MUST NOT without a bound prohibition", None, []
        dp = dict(pr, id=f"PROH-{ins.id}", kind="safety", description=f"{ins.id}: {ins.text}", scope="derived from MUST NOT", assumptions={}, bounds={}, instruction=ins.id, span=[ins.start, ins.end], modality=m)
        return COV_SINGLE, "MUST NOT: prohibition modelled as a safety property", [_o(pr.get("reading", "prohibited"), "prohibited behaviour", aligned=True, derived_property=dp, cue_span=cs)], pre
    bypass = p.get("relaxed_patch") or ([{"op": "bypass", "remove": p["hold"], "action": p["bypass_action"]}] if p.get("hold") else None)
    if m in ("MUST", "SHALL") and "optional" in p and p.get("must_reading"):
        o = p["optional"]
        return COV_SINGLE, "MUST makes the optional behaviour mandatory", [_o(p["must_reading"], "optional behaviour mandatory", [{"op": "add", "t": {"id": o["id"], "src": o["src"], "dst": o["dst"], "action": o["action"]}}], cue_span=cs)], pre
    if m in ("MUST", "SHALL"):
        if bypass and p.get("relaxed_cue") and re.search(p["relaxed_cue"], ins.text, re.I):
            return COV_SINGLE, "MUST with bound relaxing cue", [_o("relaxed", "relaxed", bypass, edit_type="change-constraint-strength", cue_span=_cue(ins.text, p["relaxed_cue"]))], pre
        return COV_SINGLE, "MUST: enforced", [_o("enforced", "enforced", aligned=True, cue_span=cs)], pre
    if m == "SHOULD" and pol.get("SHOULD") == "enforced_only":
        return COV_SINGLE, "SHOULD treated as mandatory by model policy (enforced_only)", [_o("enforced", "enforced by policy", aligned=True, cue_span=cs)], pre
    if m == "MAY" and "optional" in p:
        o = p["optional"]
        omitted = _o("omitted", "optional behaviour not implemented", aligned=False, text=p.get("omitted_text"), edit_type="change-constraint-strength", cue_span=cs)
        impl = _o("implemented", "optional behaviour implemented", [{"op": "add", "t": {"id": o["id"], "src": o["src"], "dst": o["dst"], "action": o["action"]}}],
                  aligned=True, text=p.get("implemented_text"), edit_type="change-constraint-strength", cue_span=cs)
        return COV_ANALYSED, "MAY: permitted optional path and no-optional-action path both represented", [omitted, impl], pre
    if m in ("SHOULD", "MAY") and bypass:
        enforced = _o("enforced", "treated as mandatory", aligned=(m == "SHOULD"), text=MOD_RE.sub("MUST", ins.text, 1), edit_type="change-constraint-strength", cue_span=cs)
        relaxed = _o("relaxed", "treated as optional / bypassable", bypass, aligned=(m == "MAY"), text=p.get("relaxed_text"), edit_type="change-constraint-strength", cue_span=cs)
        return COV_ANALYSED, f"{m} admits enforced and relaxed readings", [enforced, relaxed], pre
    return COV_UNANALYSED, f"{m} has no bound hold/optional behaviour in the model", None, []


def _ref(ins, b, ctx):
    p = b.get("REF")
    if not p:
        if ANAPHORA.search(ins.text): return COV_UNANALYSED, "reference-like phrase present but no antecedent binding", None, []
        return COV_INAPPLICABLE, "no REF binding", None, []
    cands = p["candidates"]
    opts = [_o(c["id"], f"phrase refers to {c['msg']}", [{"op": "rename_msg", "tid": p["transition"], "msg": c["msg"]}], aligned=(i == 0),
               text=c.get("text"), edit_type="disambiguate-reference") for i, c in enumerate(cands)]
    hits = [(o, c) for o, c in zip(opts, cands) if c.get("cue") and re.search(c["cue"], ins.text, re.I)]
    if len(hits) == 1: return COV_SINGLE, "explicit referent cue", [dict(hits[0][0], text=None, cue_span=_cue(ins.text, hits[0][1]["cue"]))], ["explicit referent"]
    if len(hits) > 1: return COV_UNANALYSED, "several explicit referents in one instruction; not resolved", None, []
    m = re.search(r"\b" + re.escape(p["phrase"]) + r"\b", ins.text, re.I)
    if not m: return COV_INAPPLICABLE, "referring phrase absent", None, []
    if len(opts) < 2: return COV_UNANALYSED, "fewer than two bound antecedents; reference not resolved", None, []
    return COV_ANALYSED, "ambiguous referent", [dict(o, cue_span=(m.start(), m.end())) for o in opts], [f"phrase '{p['phrase']}' with {len(opts)} candidate antecedents"]


def _def(ins, b, ctx):
    p = b.get("DEF")
    if not p: return COV_INAPPLICABLE, "no DEF binding", None, []
    d = ctx["defs"].get(p["term"])
    if not d: return COV_UNANALYSED, f"term '{p['term']}' missing from definition table", None, []
    senses, seen, uniq, dropped = d["senses"], {}, [], []
    for s in senses:                                    # keep only senses with distinct model behaviour
        k = frozenset(s["states"])
        if k in seen: dropped.append(s["id"]); continue
        seen[k] = s["id"]; uniq.append(s)
    opts = [_o(s["id"], f"'{p['term']}' means closed states {s['states']}", [{"op": "set_closed", "states": s["states"]}], aligned=(i == 0),
               text=s.get("text"), edit_type="fix-definition") for i, s in enumerate(uniq)]
    hits = [(o, s) for o, s in zip(opts, uniq) if s.get("cue") and re.search(s["cue"], ins.text, re.I)]
    if len(hits) == 1: return COV_SINGLE, "explicit sense cue", [dict(hits[0][0], text=None, cue_span=_cue(ins.text, hits[0][1]["cue"]))], ["explicit sense"]
    m = re.search(r"\b" + re.escape(p["term"]) + r"\b", ins.text, re.I)
    if not m: return COV_INAPPLICABLE, "defined term absent", None, []
    pre = [f"term '{p['term']}' has {len(senses)} candidate definitions (source: {d.get('source','unspecified')})"]
    da = d.get("defined_at")
    if da and da in ctx["lines"] and ctx["lines"][da] > ins.line: pre.append(f"used before being defined at {da}")
    if dropped: pre.append(f"senses {dropped} dropped: identical model behaviour")
    if len(opts) < 2: return COV_SINGLE, "all senses lead to identical model behaviour; single reading", [dict(opts[0], text=None, cue_span=(m.start(), m.end()))], pre
    return COV_ANALYSED, "term with distinct senses", [dict(o, cue_span=(m.start(), m.end())) for o in opts], pre


def _scope(ins, b, ctx):
    p = b.get("SCOPE")
    if not p: return COV_INAPPLICABLE, "no SCOPE binding", None, []
    opts = []
    for i, s in enumerate(p["scopes"]):
        patch = [{"op": "set_action", "tid": t, "action": "skip"} for t in s.get("silence", [])] + [{"op": "remove", "tid": t} for t in s.get("disable", [])]
        opts.append(_o(s["id"], f"requirement applies at scope '{s['id']}' (transitions {s.get('silence', []) + s.get('disable', [])})", patch, aligned=(i == 0),
                       text=s.get("text"), edit_type="tighten-scope"))
    effects = {frozenset((x["op"], x.get("tid")) for x in o["patch"]) for o in opts}
    hits = [(o, s) for o, s in zip(opts, p["scopes"]) if s.get("cue") and re.search(s["cue"], ins.text, re.I)]
    if len(hits) == 1: return COV_SINGLE, "explicit scope cue", [dict(hits[0][0], text=None, cue_span=_cue(ins.text, hits[0][1]["cue"]))], ["explicit scope"]
    m = re.search(p["trigger"], ins.text, re.I)
    if not m: return COV_INAPPLICABLE, "scope trigger absent", None, []
    if len(effects) < 2: return COV_SINGLE, "fewer than two scopes with distinct effect: no scope ambiguity declared", [dict(opts[0], text=None, cue_span=(m.start(), m.end()))], ["scope trigger", "scopes not distinct"]
    return COV_ANALYSED, "scope trigger with several candidate scopes", [dict(o, cue_span=(m.start(), m.end())) for o in opts], ["scope trigger", f"{len(opts)} candidate scopes"]


def _tol(ins, b, ctx):
    p = b.get("TOL")
    if not p: return COV_INAPPLICABLE, "no TOL binding", None, []
    t = ins.text
    m = NUM_RE.search(t)
    num = None
    if m: num = {"comparator": m.group(1).lower(), "value": float(m.group(2)) if "." in m.group(2) else int(m.group(2)), "unit": m.group(3), "span": [m.start(), m.end()]}
    def withc(inclusive):
        return dict(num, constraint=typed_constraint(num, inclusive)) if num else None
    for key, rid in (("inclusive_cue", "inclusive"), ("exclusive_cue", "exclusive")):
        if p.get(key) and re.search(p[key], t, re.I):
            patch = [] if rid == "inclusive" else [{"op": "remove", "tid": p["boundary_transition"]}]
            n2 = NUM_RE.search(t); numeric = None
            if n2 is None:                                  # cue phrases such as 'up to and including 5 seconds'
                n3 = re.search(r"(\d+(?:\.\d+)?)\s*([A-Za-z]+)", t)
                if n3: num = {"comparator": "within", "value": float(n3.group(1)) if "." in n3.group(1) else int(n3.group(1)), "unit": n3.group(2), "span": [n3.start(), n3.end()]}
            numeric = withc(rid == "inclusive")
            return COV_SINGLE, f"explicit {rid} boundary cue", [_o(rid, rid, patch, aligned=(rid == "inclusive"), numeric=numeric, cue_span=_cue(t, p[key]))], [f"explicit {rid} cue"]
    vary = re.search(r"\b(may vary|tolerat\w*)\b", t, re.I)
    if not m and not vary: return COV_INAPPLICABLE, "tolerance cue absent", None, []
    if m and m.group(1).lower() in ("approximately", "about"):
        if not p.get("tolerance"):
            return COV_UNANALYSED, f"'{m.group(1)}' value without a defined tolerance; not interpreted as a precise range", None, []
        add = {"op": "add", "t": dict(p["tolerance"]["transition"])}
        return COV_ANALYSED, "approximate value with model-defined tolerance", [_o("strict", "exact value only", aligned=True, numeric=num, text=p.get("strict_text"), edit_type="fix-tolerance"),
                                                                              _o("tolerant", f"values within defined tolerance {p['tolerance'].get('range')}", [add], numeric=num, text=p.get("tolerant_text"), edit_type="fix-tolerance")], ["approximate + defined tolerance"]
    if m and p.get("boundary_transition"):
        if m.group(3) is None or m.group(3).lower() not in UNIT_SECONDS:
            return COV_UNANALYSED, f"numeric limit '{m.group(2)}' has a missing or unsupported unit; not guessed", None, []
        return COV_ANALYSED, f"'{m.group(1)}' leaves the boundary value ambiguous", [
            _o("inclusive", "boundary value accepted", aligned=True, numeric=withc(True), text=p.get("inclusive_text"), edit_type="fix-tolerance", cue_span=(m.start(), m.end())),
            _o("exclusive", "boundary value rejected", [{"op": "remove", "tid": p["boundary_transition"]}], numeric=withc(False), text=p.get("exclusive_text"), edit_type="fix-tolerance", cue_span=(m.start(), m.end()))], \
            [f"{m.group(1)} {m.group(2)} {m.group(3) or ''}".strip(), "boundary transition bound", "typed constraint attached (value, unit, comparator, bounds, inclusivity)"]
    if vary and p.get("tolerance"):
        add = {"op": "add", "t": dict(p["tolerance"]["transition"])}
        return COV_ANALYSED, "'may vary' with defined tolerance", [_o("strict", "exact", aligned=True), _o("tolerant", "variant accepted", [add])], ["may vary + tolerance"]
    return COV_UNANALYSED, "tolerance expression without a bound boundary/tolerance model", None, []


OPS = [("ORDER", "ORDER-1", _order), ("MODALITY", "MOD-1", _modality), ("REF", "REF-1", _ref),
       ("DEF", "DEF-1", _def), ("SCOPE", "SCOPE-1", _scope), ("TOL", "TOL-1", _tol)]


def _affected(patch):
    out = []
    for p in patch:
        o = p["op"]
        if o in ("bypass", "remove", "rename_msg", "set_action"): out.append({"kind": "transition", "id": p.get("remove") or p["tid"], "op": o})
        elif o == "add": out.append({"kind": "transition(added)", "id": p["t"]["id"], "op": o})
        elif o == "set_closed": out.append({"kind": "states", "id": p["states"], "op": o})
    return out


def derive_instruction(ins, binding, ctx):
    """Return (readings, coverage records, instruction-level status)."""
    cov, fired, unanalysed = [], [], False
    if not binding:
        cov.append(CoverageRecord(ins.id, "-", COV_UNANALYSED, "no model binding: instruction not connected to the FSM model"))
        return [], cov, COV_UNANALYSED
    for name, rid, fn in OPS:
        st, why, opts, pre = fn(ins, binding, ctx)
        cov.append(CoverageRecord(ins.id, rid, st, why))
        if st in (COV_ANALYSED, COV_SINGLE): fired.append((name, rid, opts, pre))
        if st == COV_UNANALYSED: unanalysed = True
    if unanalysed or not fired:
        if not fired and not unanalysed: cov.append(CoverageRecord(ins.id, "-", COV_UNANALYSED, "no supported operator applies; NOT treated as unambiguous"))
        return [], cov, COV_UNANALYSED
    readings = []
    for combo in itertools.product(*[f[2] for f in fired]):
        rid = "+".join(o["id"] for o in combo) if len(fired) == 1 else "+".join(f"{f[0]}:{o['id']}" for f, o in zip(fired, combo))
        pre = [x for f in fired for x in f[3]]
        patch = [p for o in combo for p in o["patch"]]
        dp = next((o["derived_property"] for o in combo if o.get("derived_property")), None)
        readings.append(ReadingRecord(
            ins.id, (ins.start, ins.end), "+".join(f[1] for f in fired), RULE_SET_VERSION, "+".join(f[0] for f in fired), rid, pre,
            "; ".join(o["desc"] for o in combo), patch, all(o["aligned"] for o in combo),
            ins.errata or ["(no errata link supplied)"], COV_ANALYSED, combo[0]["text"] if len(fired) == 1 else None,
            ins.text, _affected(patch), f"{'+'.join(f[1] for f in fired)}: " + "; ".join(pre), [f"rule-set {RULE_SET_VERSION}", "channel/environment assumptions from model.system"],
            "generated", next((o["numeric"] for o in combo if o.get("numeric")), None), dp,
            next((o["cue_span"] for o in combo if o.get("cue_span")), None), combo[0].get("edit_type", "") if len(fired) == 1 else "composite"))
    return readings, cov, (COV_ANALYSED if len(readings) > 1 else COV_SINGLE)


def derive_readings(text: str, model: dict) -> dict:
    """Full analysis of a specification text: anchored instructions, readings, coverage, definition table."""
    ins_list = anchor(text, model)
    ctx = {"defs": model.get("definitions", {}), "lines": {i.id: i.line for i in ins_list}, "policy": dict(DEFAULT_POLICY, **model.get("policy", {}))}
    readings, coverage, status = {}, [], {}
    for ins in ins_list:
        r, c, s = derive_instruction(ins, model.get("bindings", {}).get(ins.id), ctx)
        readings[ins.id], status[ins.id] = r, s
        coverage += c
    dtab = [{"term": t, "candidates": [s["id"] for s in d["senses"]], "source": d.get("source"),
             "affected_instructions": [i.id for i in ins_list if t in i.references]} for t, d in ctx["defs"].items()]
    return {"text": text, "sha256": sha256(text), "instructions": ins_list, "readings": readings, "coverage": coverage,
            "status": status, "rule_set_version": RULE_SET_VERSION, "policy": ctx["policy"], "definition_table": dtab}


def derived_properties(analysis) -> list:
    return [r.derived_property for rs in analysis["readings"].values() for r in rs if r.derived_property]


def apply_edits_to_text(text: str, edits: list) -> str:
    """Replace instruction text by ID, keeping tags and every untouched line byte-identical."""
    lines = text.splitlines(keepends=True)
    for e in edits:
        for i, ln in enumerate(lines):
            m = TAG_RE.match(ln)
            if m and m.group(1) == e["instruction_id"]:
                nl = "\n" if ln.endswith("\n") else ""
                lines[i] = f"[{e['instruction_id']}] {e['new_text']}{nl}"
    return "".join(lines)
