"""Feature 10: conformance-test sequences from the verified model, tied to verification evidence.

execution_status is one of: generated | replayed_in_model | executed_against_implementation.
Only the independent checker can move a test to replayed_in_model; only an external run (mark_executed) can
move it to executed_against_implementation. A generated suite is NOT evidence that a real implementation passed.
"""
from __future__ import annotations
import hashlib, json
from .models import ConformanceTest
from .fsm import build_fsms, explore, bounded_words, _path
from .tolerance import boundary_table
from .engine import profile_readings, bad_safe, profile_dict


def _sig(kind, steps): return hashlib.sha256(json.dumps([kind, [(s.get("impl"), s.get("tid", s.get("action"))) for s in steps]]).encode()).hexdigest()[:12]


def _wg(analysis, model, V, pr, limits, depth):
    g = explore(build_fsms(model, profile_readings(analysis, model, V["slots"], V["fixed"], pr)), model["system"], limits["max_states"])
    return bounded_words(g, depth, limits.get("max_words", 20000))[0], g


def _word_steps(g, word):
    """Map an observable word to a concrete run (with transition ids) so the checker can replay it."""
    memo = {}
    def go(st, i):
        if i == len(word): return []
        if (st, i) in memo: return memo[(st, i)]
        for n, t, ns in g["succ"].get(st, []):
            if (n, t["action"]) == word[i]:
                r = go(ns, i + 1)
                if r is not None: memo[(st, i)] = [{"impl": n, "tid": t["id"], "action": t["action"]}] + r; return memo[(st, i)]
        memo[(st, i)] = None
        return None
    return go(g["init"], 0)


def _finish(tests):
    seen = {}
    for t in tests:
        sg = _sig(t["kind"], t["steps"]); t["signature"] = sg
        t["duplicate_of"] = seen.get(sg)
        seen.setdefault(sg, t["id"])
    return tests


def _mk(tests, kind, setup, steps, expected, targets, instrs, prop, spec_sha, claim, pre, assumptions, expected_transitions=None):
    t = ConformanceTest(f"CT-{len(tests)+1:03d}", setup, steps, expected, targets, assumptions).to_dict()
    t.update(kind=kind, source_instructions=sorted(set(instrs)), motivating_property=prop, preconditions=pre, expected_transitions=expected_transitions or [],
             execution_status="generated", traceability={"spec_sha256": spec_sha, "certificate_claim": claim})
    tests.append(t)


def generate_tests(analysis, model, V, limits, R=None, iut=None):
    slots, fixed = V["slots"], V["fixed"]
    _, safe, inc = bad_safe(V)
    iut = iut or sorted(model["system"]["implementations"])[0]
    assum = {"channel_capacity": model["system"].get("channel_capacity"), **model["system"].get("assumptions", {})}
    tests = []
    for pr in sorted(safe):
        fsms = build_fsms(model, profile_readings(analysis, model, slots, fixed, pr))
        g = explore(fsms, model["system"], limits["max_states"]); first = {}
        for s in g["order"]:
            par = g["parent"][s]
            if par and par[1] == iut and (pr, par[2]["id"]) not in first: first[(pr, par[2]["id"])] = s
        for (_, tid), s in sorted(first.items(), key=lambda kv: kv[0][1]):
            path = _path(g, s)
            steps = [{"impl": n, "tid": t["id"], "action": t["action"]} for n, t, _ in path]
            tags = [t.get("tag", "base") for _, t, _ in path]
            instrs = [x.split(":")[0] for x in tags if x != "base"] or [i.id for i in analysis["instructions"]]
            prev, trans = g["init"], []
            for n, t, st in path:
                i = g["names"].index(n); trans.append({"impl": n, "from": prev[0][i], "to": st[0][i], "action": t["action"]}); prev = st
            _mk(tests, "normal_success_coverage", {"implementation_under_test": iut, "profile": list(pr), "profile_readings": profile_dict(slots, pr), "model_version": "revised",
                                                    "reference_peer": "verified model of the other implementation(s)"}, steps,
                {"iut_inputs": [x["action"] for x in steps if x["impl"] == iut and x["action"][0] == "?"], "iut_outputs": [x["action"] for x in steps if x["impl"] == iut and x["action"][0] == "!"],
                 "final_locals": dict(zip(g["names"], s[0])), "channels_non_empty": any(s[1])},
                f"covers transition {tid}", instrs, ",".join(sorted(res for res in V["table"][pr]["results"])), analysis["sha256"], f"profile {list(pr)}: all selected properties",
                {"initial_locals": dict(zip(g["names"], g["init"][0])), "channels": "empty"}, assum, trans)
    depth = limits["behaviour_depth"]
    for k, (impl, ins) in enumerate(slots):               # alternative readings that are both safe
        dom = V["domains"][(impl, ins)]
        for a in range(len(dom)):
            for b in range(a + 1, len(dom)):
                for pr in sorted(safe):
                    pr2 = pr[:k] + (dom[b],) + pr[k + 1:]
                    if pr[k] != dom[a] or pr2 not in safe: continue
                    (w1, g1), (w2, g2) = [_wg(analysis, model, V, p, limits, depth) for p in (pr, pr2)]
                    diff = sorted(w1 ^ w2, key=lambda x: (len(x), x))
                    ids = {"instruction": ins, "baseline_reading": dom[a], "alternative_reading": dom[b], "depth": depth}
                    if diff:
                        first = diff[0] in w1; steps = _word_steps(g1 if first else g2, diff[0])
                        _mk(tests, "distinguishing_safe_alternatives", {"implementation_under_test": impl, "profile": list(pr if first else pr2), "alternative_profile": list(pr2 if first else pr), "model_version": "revised", **ids},
                            steps or [{"impl": n, "action": act} for n, act in diff[0]], {"observable_only_under": dom[a] if first else dom[b]},
                            f"distinguishes reading {dom[a]} vs {dom[b]} of {ins} for {impl}", [ins], None, analysis["sha256"], "remaining open reading", {}, {"depth": depth})
                    else:
                        _mk(tests, "no_difference_found", {"profile": list(pr), "alternative_profile": list(pr2), "model_version": "revised", **ids}, [],
                            {"outcome": f"no observable difference between the readings within depth {depth}; no distinguishing test invented"}, f"readings {dom[a]} / {dom[b]} of {ins} indistinguishable within bound", [ins], None, analysis["sha256"], "remaining open reading", {}, {"depth": depth})
                        tests[-1]["execution_status"] = "not_applicable"
                    break
    for pr in sorted(inc):                                 # intentionally unknown expectations
        _mk(tests, "expected_result_unknown", {"profile": list(pr), "model_version": "revised"}, [], {"outcome": "UNKNOWN: verification incomplete for this profile"},
            "profile not fully verified", [], None, analysis["sha256"], f"profile {list(pr)} INCOMPLETE", {}, assum)
    if R:                                                  # per-operator alternative-reading / boundary-condition tests (original model)
        A0, V0 = R["analysis0"], R["V0"]
        if not V0["truncated"]:
            base = tuple(V0["domains"][x][0] for x in V0["slots"])
            for k, (impl, ins) in enumerate(V0["slots"]):
                op = A0["readings"][ins][0].operator
                if op not in ("TOL", "REF", "DEF", "SCOPE"): continue
                kind = "boundary_condition" if op == "TOL" else f"alternative_reading_{op}"
                for rid in V0["domains"][(impl, ins)][1:]:
                    alt = base[:k] + (rid,) + base[k + 1:]
                    (w1, g1), (w2, g2) = [_wg(A0, model, V0, p, limits, depth) for p in (base, alt)]
                    diff = sorted(w1 ^ w2, key=lambda x: (len(x), x))
                    rd = next(r for r in A0["readings"][ins] if r.reading_id == rid); rd0 = A0["readings"][ins][0]
                    ids = {"instruction": ins, "operator": op, "baseline_reading": V0["domains"][(impl, ins)][0], "alternative_reading": rid, "depth": depth}
                    exp = {"baseline_status": V0["table"][base]["status"], "alternative_status": V0["table"][alt]["status"], "numeric": rd.numeric}
                    if op == "TOL" and rd.numeric and rd0.numeric and rd.numeric.get("constraint") and rd0.numeric.get("constraint"):
                        exp["boundary_values"] = {"baseline_reading": boundary_table(rd0.numeric["constraint"]), "alternative_reading": boundary_table(rd.numeric["constraint"])}
                    if diff:
                        first = diff[0] in w1; steps = _word_steps(g1 if first else g2, diff[0])
                        _mk(tests, kind, {"profile": list(base if first else alt), "alternative_profile": list(alt if first else base), "model_version": "original", **ids},
                            steps or [{"impl": n, "action": act} for n, act in diff[0]], dict(exp, observable_only_under="baseline" if first else "alternative"),
                            f"{op}: distinguishes baseline reading '{ids['baseline_reading']}' from '{rid}' of {ins}" + (f" (value {rd.numeric['value']} {rd.numeric['unit']}, {rd.numeric['comparator']})" if rd.numeric else ""),
                            [ins], None, A0["sha256"], f"original: slot {impl}::{ins}", {}, {"depth": depth})
                    else:
                        _mk(tests, "no_difference_found", {"profile": list(base), "alternative_profile": list(alt), "model_version": "original", **ids}, [],
                            dict(exp, outcome=f"no observable difference within depth {depth}; no distinguishing test invented"), f"{op}: readings '{ids['baseline_reading']}' / '{rid}' indistinguishable within bound", [ins], None, A0["sha256"], f"original: slot {impl}::{ins}", {}, {"depth": depth})
                        tests[-1]["execution_status"] = "not_applicable"
    if R and R.get("witnesses"):
        A0, seen = R["analysis0"], set()
        for w in R["witnesses"]:
            key = (w["property_id"], json.dumps(w["minimal_combinations"]["combinations"], sort_keys=True))
            if key in seen or not w["trace"]: continue
            seen.add(key)
            prof = tuple(w["profile"][f"{i}::{s}"] for i, s in R["V0"]["slots"])
            steps = [{"impl": s["impl"], "tid": s["tid"], "action": s["action"]} for s in w["trace"]]
            _mk(tests, "counterexample", {"profile": list(prof), "profile_readings": w["profile"], "model_version": "original"}, steps,
                {"outcome": f"property {w['property_id']} violated by this sequence under the ORIGINAL reading profile", "witness_kind": w["witness_kind"]},
                f"reproduces counterexample for {w['property_id']}", w["instruction_ids"], w["property_id"], R["analysis0"]["sha256"], f"original: profile {list(prof)} / {w['property_id']}", {}, assum)
            if R.get("edits") and R.get("A1") is not R["analysis0"]:
                A1, V1 = R["A1"], R["V1"]
                ok = False
                try:
                    from .engine import profile_space
                    s1, d1, f1 = profile_space(A1, model)
                    pr1 = tuple(next(iter(d1[x])) for x in s1)
                    fs = build_fsms(model, profile_readings(A1, model, s1, f1, pr1)); g1 = explore(fs, model["system"], limits["max_states"])
                    cur, ok = g1["init"], True
                    for st in steps:
                        nxt = next((ns for n, t, ns in g1["succ"].get(cur, []) if n == st["impl"] and t["id"] == st["tid"]), None)
                        if nxt is None: ok = False; break
                        cur = nxt
                except Exception: ok = False
                _mk(tests, "clarification_regression", {"profile": list(prof), "model_version": "revised"}, steps,
                    {"outcome": "a conforming implementation of the REVISED specification must not be able to produce this sequence",
                     "model_check": "sequence not enabled in revised baseline model" if not ok else "sequence STILL enabled in revised baseline model"},
                    f"clarification intended to remove the {w['property_id']} violation", w["instruction_ids"], w["property_id"], R["A1"]["sha256"], "revised: targeted profiles removed", {}, assum)
    return _finish(tests)


def mark_executed(tests, test_id, passed, implementation, notes="", **details):
    """Record an EXTERNAL execution result; the only way a test reaches executed_against_implementation."""
    for t in tests:
        if t["id"] == test_id:
            t["execution_status"] = "executed_against_implementation"
            t["external_result"] = dict({"passed": passed, "implementation": implementation, "notes": notes}, **details)
    return tests
