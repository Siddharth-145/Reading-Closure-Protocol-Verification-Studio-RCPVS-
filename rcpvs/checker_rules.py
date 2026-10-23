"""Checker-side reading derivation (Task 4). Written independently of spec_analysis.py: it does NOT import it.

Shared with the engine ONLY by documentation: the rule-set version string, the model/binding schema, and the model
semantics (patch operations). A differential test (tests/test_checker.py) compares this derivation with the engine's on
every example; a bug present in both would still go undetected, which is stated in the README."""
from __future__ import annotations
import hashlib, itertools, re
from types import SimpleNamespace as NS

RULE_SET_VERSION = "2.0.0"
_POLICY = {"MUST": "enforced", "SHOULD": "both_readings", "MAY": "both_readings", "MUST NOT": "derived_safety_property"}
_LINE = re.compile(r"^\s*\[(I-[\w.]+)\]\s*(.+?)\s*$")
_MOD = re.compile(r"\b(MUST NOT|MUST|SHALL|SHOULD|MAY)\b")
_ANA = re.compile(r"\b(it|they|them|that|the previous (?:request|message))\b", re.I)
_NUM = re.compile(r"\b(within|at least|at most|up to|approximately|about|no more than|no less than)\s+(\d+(?:\.\d+)?)\s*([A-Za-z]+)?", re.I)
_UNITS = {"ms", "millisecond", "milliseconds", "s", "sec", "secs", "second", "seconds", "min", "minute", "minutes"}
UN, SI, IN, AN = "UNANALYSED", "ANALYSED_SINGLE", "INAPPLICABLE", "ANALYSED"


def sha(s): return hashlib.sha256(s.encode()).hexdigest()


def anchor(text):
    out, off = [], 0
    for no, raw in enumerate(text.splitlines(True), 1):
        st = raw.strip()
        if st and not st.startswith("#"):
            m = _LINE.match(raw); body = m.group(2) if m else st
            iid = m.group(1) if m else "I-H" + sha(" ".join(body.lower().split()))[:6]
            col0 = raw.find(body); md = _MOD.search(body)
            out.append(NS(id=iid, line=no, col=col0 + 1, start=off + col0, end=off + col0 + len(body), text=body, modality=md.group(1) if md else None, text_sha256=sha(body)))
        off += len(raw)
    return out


def _s(rx, t): return re.search(rx, t, re.I)


def _bypass(first, action): return [{"op": "bypass", "remove": first, "action": action}]


def _order(i, b, c):
    p = b.get("ORDER"); t = i.text
    if not p: return IN, None
    O, U = ("ordered", []), ("unordered", _bypass(p["first"], p["second"]))
    if re.search(r"\bMUST\b.*\bbefore\b", t): return SI, [O]
    if re.search(r"\bMAY\b.*\bbefore\b.*\bcompleted\b", t): return SI, [U]
    if re.search(r"\b(before|prior to|only after|after completing)\b", t): return UN, None
    if re.search(r"\b(sends?|transmits?)\b.*?\b(and|then)\b.*?\b(clos\w*|terminat\w*)", t, re.I): return AN, [O, U]
    return IN, None


def _add(o): return [{"op": "add", "t": {"id": o["id"], "src": o["src"], "dst": o["dst"], "action": o["action"]}}]


def _mod(i, b, c):
    p = b.get("MODALITY"); m = i.modality
    if not p or m is None: return IN, None
    if m == "MUST NOT":
        pr = p.get("prohibit")
        if not pr: return UN, None
        return SI, [(pr.get("reading", "prohibited"), [])]
    byp = p.get("relaxed_patch") or (_bypass(p["hold"], p["bypass_action"]) if p.get("hold") else None)
    if m in ("MUST", "SHALL"):
        if "optional" in p and p.get("must_reading"): return SI, [(p["must_reading"], _add(p["optional"]))]
        if byp and p.get("relaxed_cue") and _s(p["relaxed_cue"], i.text): return SI, [("relaxed", byp)]
        return SI, [("enforced", [])]
    if m == "SHOULD" and c["policy"].get("SHOULD") == "enforced_only": return SI, [("enforced", [])]
    if m == "MAY" and "optional" in p: return AN, [("omitted", []), ("implemented", _add(p["optional"]))]
    if m in ("SHOULD", "MAY") and byp: return AN, [("enforced", []), ("relaxed", byp)]
    return UN, None


def _ref(i, b, c):
    p = b.get("REF"); t = i.text
    if not p: return (UN, None) if _ANA.search(t) else (IN, None)
    opts = [(k["id"], [{"op": "rename_msg", "tid": p["transition"], "msg": k["msg"]}]) for k in p["candidates"]]
    hit = [o for o, k in zip(opts, p["candidates"]) if k.get("cue") and _s(k["cue"], t)]
    if len(hit) == 1: return SI, hit
    if len(hit) > 1: return UN, None
    if not _s(r"\b" + re.escape(p["phrase"]) + r"\b", t): return IN, None
    return (AN, opts) if len(opts) > 1 else (UN, None)


def _def(i, b, c):
    p = b.get("DEF"); t = i.text
    if not p: return IN, None
    d = c["defs"].get(p["term"])
    if not d: return UN, None
    seen, uniq = set(), []
    for s in d["senses"]:
        k = frozenset(s["states"])
        if k not in seen: seen.add(k); uniq.append(s)
    opts = [(s["id"], [{"op": "set_closed", "states": s["states"]}]) for s in uniq]
    hit = [o for o, s in zip(opts, uniq) if s.get("cue") and _s(s["cue"], t)]
    if len(hit) == 1: return SI, hit
    if not _s(r"\b" + re.escape(p["term"]) + r"\b", t): return IN, None
    return (SI, [opts[0]]) if len(opts) < 2 else (AN, opts)


def _scope(i, b, c):
    p = b.get("SCOPE"); t = i.text
    if not p: return IN, None
    opts = [(s["id"], [{"op": "set_action", "tid": x, "action": "skip"} for x in s.get("silence", [])] + [{"op": "remove", "tid": x} for x in s.get("disable", [])]) for s in p["scopes"]]
    eff = {frozenset((q["op"], q.get("tid")) for q in o[1]) for o in opts}
    hit = [o for o, s in zip(opts, p["scopes"]) if s.get("cue") and _s(s["cue"], t)]
    if len(hit) == 1: return SI, hit
    if not _s(p["trigger"], t): return IN, None
    return (SI, [opts[0]]) if len(eff) < 2 else (AN, opts)


def _tol(i, b, c):
    p = b.get("TOL"); t = i.text
    if not p: return IN, None
    for key, rid in (("inclusive_cue", "inclusive"), ("exclusive_cue", "exclusive")):
        if p.get(key) and _s(p[key], t): return SI, [(rid, [] if rid == "inclusive" else [{"op": "remove", "tid": p["boundary_transition"]}])]
    m = _NUM.search(t); vary = _s(r"\b(may vary|tolerat\w*)\b", t)
    if not m and not vary: return IN, None
    tol = [("strict", []), ("tolerant", [{"op": "add", "t": dict(p["tolerance"]["transition"])}])] if p.get("tolerance") else None
    if m and m.group(1).lower() in ("approximately", "about"): return (AN, tol) if tol else (UN, None)
    if m and p.get("boundary_transition"):
        if m.group(3) is None or m.group(3).lower() not in _UNITS: return UN, None
        return AN, [("inclusive", []), ("exclusive", [{"op": "remove", "tid": p["boundary_transition"]}])]
    if vary and tol: return AN, tol
    return UN, None


_OPS = [("ORDER", "ORDER-1", _order), ("MODALITY", "MOD-1", _mod), ("REF", "REF-1", _ref), ("DEF", "DEF-1", _def), ("SCOPE", "SCOPE-1", _scope), ("TOL", "TOL-1", _tol)]


def derive(text, model):
    ctx = {"defs": model.get("definitions", {}), "policy": dict(_POLICY, **model.get("policy", {}))}
    ins = anchor(text); rd, cov, st = {}, [], {}
    for i in ins:
        b = model.get("bindings", {}).get(i.id)
        if not b: rd[i.id], st[i.id] = [], UN; cov.append(NS(instruction_id=i.id, rule_id="-", status=UN)); continue
        fired, bad = [], False
        for name, rid, fn in _OPS:
            s, o = fn(i, b, ctx); cov.append(NS(instruction_id=i.id, rule_id=rid, status=s))
            if s in (AN, SI): fired.append((rid, o))
            bad |= s == UN
        if bad or not fired:
            if not fired and not bad: cov.append(NS(instruction_id=i.id, rule_id="-", status=UN))
            rd[i.id], st[i.id] = [], UN; continue
        names = [n for n, r, f in _OPS if any(r == x[0] for x in fired)]
        out = []
        for combo in itertools.product(*[f[1] for f in fired]):
            rid = "+".join(o[0] for o in combo) if len(fired) == 1 else "+".join(f"{n}:{o[0]}" for n, o in zip(names, combo))
            out.append(NS(instruction_id=i.id, reading_id=rid, patch=[q for o in combo for q in o[1]], rule_id="+".join(f[0] for f in fired),
                          rule_version=RULE_SET_VERSION, span=(i.start, i.end)))
        rd[i.id], st[i.id] = out, (AN if len(out) > 1 else SI)
    return {"text": text, "sha256": sha(text), "instructions": ins, "readings": rd, "coverage": cov, "status": st, "derived_ids": sorted(
        f"PROH-{i.id}" for i in ins if i.modality == "MUST NOT" and rd.get(i.id) and model.get("bindings", {}).get(i.id, {}).get("MODALITY", {}).get("prohibit"))}


def apply_edits(text, edits):
    lines = text.splitlines(True)
    for e in edits:
        for k, ln in enumerate(lines):
            m = _LINE.match(ln)
            if m and m.group(1) == e["instruction_id"]: lines[k] = f"[{e['instruction_id']}] {e['new_text']}" + ("\n" if ln.endswith("\n") else "")
    return "".join(lines)


def patch_digest(patch): return sha(repr(sorted(repr(sorted(p.items(), key=str)) for p in patch)))
