"""Features 3-7: deployment profiles, verification, cause attribution, conditional nogoods,
minimal-impact clarification (MIRA), re-reading and iterative re-verification.

Definitions used throughout
  * profile: assignment of one reading to every (implementation, instruction) slot with >=2 readings.
  * violating profile: some selected property has a VIOLATION_FOUND result for it.
  * minimal violating combination (per profile+property): a set S of non-baseline literals such that the profile
    that sets exactly S (all other slots at their baseline reading) violates the property and NO proper subset of S does.
    'exhaustive' is True when all subsets were tested, False when a greedy 1-minimal fallback was used.
  * conditional nogood: a prime implicant (minimal partial assignment) of the violating-profile set: every profile
    containing these literals violates a property. Valid only under the recorded model assumptions.
  * optimiser objective (lexicographic): hit every nogood [hard] > fewest edits > least latitude loss > shortest,
    most source-aligned wording.
"""
from __future__ import annotations
import itertools, json
from .models import *
from .spec_analysis import derive_readings, apply_edits_to_text, sha256, derived_properties
from .validate import check_or_raise, validate_readings, InputError
from .fsm import build_fsms, explore, check_property, bounded_words

DEFAULT_LIMITS = {"max_states": 100000, "max_profiles": 5000, "max_rounds": 3, "behaviour_depth": 10, "max_words": 20000,
                  "exhaustive_minimisation_max_literals": 12, "max_combos": 200000, "property_policy": "rederive", "optimiser": "enumeration"}


# ---------------------------------------------------------------- profiles (Feature 3)
def profile_space(analysis, model):
    slots, domains, fixed = [], {}, {}
    for impl, cfg in sorted(model["system"]["implementations"].items()):
        for ins in analysis["instructions"]:
            b = model.get("bindings", {}).get(ins.id)
            if not b or b.get("role") != cfg["role"]: continue
            rs = analysis["readings"][ins.id]
            if len(rs) > 1: slots.append((impl, ins.id)); domains[(impl, ins.id)] = [r.reading_id for r in rs]
            elif len(rs) == 1: fixed[(impl, ins.id)] = rs[0]
    return slots, domains, fixed


def reading_lookup(analysis, instr, rid):
    return next(r for r in analysis["readings"][instr] if r.reading_id == rid)


def profile_readings(analysis, model, slots, fixed, profile):
    by = {n: [] for n in model["system"]["implementations"]}
    for (impl, _), r in fixed.items(): by[impl].append(r)
    for (impl, ins), rid in zip(slots, profile): by[impl].append(reading_lookup(analysis, ins, rid))
    return by


def classify(slots, profile):
    """'mixed' iff some instruction is read differently by two implementations; identical readings are common-mode."""
    per = {}
    for (impl, ins), rid in zip(slots, profile): per.setdefault(ins, []).append(rid)
    return "mixed" if any(len(v) > 1 and len(set(v)) > 1 for v in per.values()) else "common-mode"


def profile_dict(slots, profile): return {f"{i}::{s}": r for (i, s), r in zip(slots, profile)}


def verify_all(analysis, model, props, limits):
    slots, domains, fixed = profile_space(analysis, model)
    total = 1
    for s in slots: total *= len(domains[s])
    truncated = total > limits["max_profiles"]
    it = itertools.product(*[domains[s] for s in slots])
    if truncated: it = itertools.islice(it, limits["max_profiles"])
    table, declared = {}, model.get("messages")
    for profile in it:
        fsms = build_fsms(model, profile_readings(analysis, model, slots, fixed, profile))
        g = explore(fsms, model["system"], limits["max_states"])
        res = {}
        for p in props:
            r = check_property(p, fsms, g, model["system"], declared)
            r["bounds"] = {"max_states": limits["max_states"], "channel_capacity": model["system"]["channel_capacity"]}
            r["profile"] = profile_dict(slots, profile)
            res[p["id"]] = r
        sts = [r["status"] for r in res.values()]
        status = VIOLATION if VIOLATION in sts else (INCOMPLETE if INCOMPLETE in sts else VERIFIED_SAFE)
        table[profile] = {"results": res, "status": status, "class": classify(slots, profile)}
    return {"slots": slots, "domains": domains, "fixed": fixed, "table": table, "profiles_total": total,
            "profiles_checked": len(table), "truncated": truncated,
            "limit_note": (f"profile space {total} exceeds max_profiles={limits['max_profiles']}: only the first {len(table)} profiles "
                           f"(lexicographic order) were checked; the remaining {total - len(table)} were NOT checked, so no safe verdict is issued") if truncated else None}


def bad_safe(V):
    t = V["table"]
    return ({p for p, r in t.items() if r["status"] == VIOLATION}, {p for p, r in t.items() if r["status"] == VERIFIED_SAFE},
            {p for p, r in t.items() if r["status"] == INCOMPLETE})


# ---------------------------------------------------------------- Feature 5: witnesses, minimal combos, attribution
def minimal_combinations(V, profile, pid, limits):
    slots, dom, t = V["slots"], V["domains"], V["table"]
    base = tuple(dom[s][0] for s in slots)
    nb = [i for i, s in enumerate(slots) if profile[i] != base[i]]
    missing = [False]
    def viol(S):
        key = tuple(profile[i] if i in S else base[i] for i in range(len(slots)))
        if key not in t: missing[0] = True; return False
        return t[key]["results"][pid]["status"] == VIOLATION
    exhaustive = len(nb) <= limits["exhaustive_minimisation_max_literals"]
    found = []
    if exhaustive:
        for k in range(len(nb) + 1):
            for S in itertools.combinations(nb, k):
                if not any(set(f) <= set(S) for f in found) and viol(set(S)): found.append(S)
    else:
        S = set(nb)
        for i in list(nb):
            if viol(S - {i}): S -= {i}
        found = [tuple(sorted(S))]
    lit = lambda i: {"impl": slots[i][0], "instruction": slots[i][1], "reading": profile[i]}
    return [[lit(i) for i in S] for S in found], exhaustive and not missing[0], tuple(sorted(nb)) in [tuple(sorted(f)) for f in found]


def attribution(analysis, tags_and_lits):
    out, ins_by = [], {i.id: i for i in analysis["instructions"]}
    for instr, rid, why in sorted(tags_and_lits):
        try: rd = reading_lookup(analysis, instr, rid)
        except StopIteration: continue
        ins = ins_by[instr]
        out.append({"instruction": instr, "line": ins.line, "col": ins.col, "span": [ins.start, ins.end], "original_wording": ins.text,
                    "reading": rid, "reading_description": rd.description, "affected": rd.affected, "rule": rd.rule_id,
                    "rule_version": rd.rule_version, "why_generated": rd.why, "contribution": why})
    return out


def witnesses(analysis, V, limits):
    out = []
    for prof, rec in V["table"].items():
        for pid, r in rec["results"].items():
            if r["status"] != VIOLATION: continue
            tags = sorted({s["reading"] for s in r["trace"] if s["reading"] != "base"})
            ids = sorted({t.split(":")[0] for t in tags})
            rules = sorted({rd.rule_id for i in ids for rd in analysis["readings"].get(i, [])})
            mins, exh, is_min = minimal_combinations(V, prof, pid, limits)
            attr = {(t.split(":", 1)[0], t.split(":", 1)[1], f"transition tagged {t} occurs in the counterexample trace") for t in tags}
            for c in mins:
                for l in c: attr.add((l["instruction"], l["reading"], "member of a minimal violating combination (changing it back removes the violation)"))
            w = ViolationWitness(profile_dict(V["slots"], prof), pid, r["trace"], tags,
                                 {"combinations": mins, "subset_minimal_exhaustive": exh, "profile_is_itself_minimal": is_min,
                                  "definition": "no proper subset of a listed combination, with all other slots at baseline, reproduces this violation"},
                                 ids, rules).to_dict()
            out.append(w | {"class": rec["class"], "witness_kind": r.get("witness_kind"), "attribution": attr and attribution(analysis, attr)})
    return out


# ---------------------------------------------------------------- Feature 6: conditional nogoods
def prime_cubes(slots, dom, bad, allp):
    cubes, n = [], len(slots)
    for size in range(1, n + 1):
        for pos in itertools.combinations(range(n), size):
            for vals in itertools.product(*[dom[slots[p]] for p in pos]):
                cube = dict(zip(pos, vals))
                if any(all(cube.get(p) == v for p, v in c.items()) for c in cubes): continue
                comp = [pr for pr in allp if all(pr[p] == v for p, v in cube.items())]
                if comp and all(pr in bad for pr in comp): cubes.append(cube)
    return cubes


def derive_nogoods(V, model, analysis=None):
    bad, _, _ = bad_safe(V); slots, dom, t = V["slots"], V["domains"], V["table"]
    cubes = prime_cubes(slots, dom, bad, set(t))
    aid = sha256(json.dumps(model["system"], sort_keys=True))[:16]
    out = []
    for k, cube in enumerate(cubes, 1):
        comp = [pr for pr in t if all(pr[p] == v for p, v in cube.items())]
        props = sorted({pid for pr in comp for pid, r in t[pr]["results"].items() if r["status"] == VIOLATION})
        ev = next((pr for pr in comp if t[pr]["results"][props[0]]["status"] == VIOLATION), comp[0])
        lits = [(slots[p][0], slots[p][1], v) for p, v in cube.items()]
        out.append(ConditionalNogood(
            f"NG-{k:02d}", lits,
            {"properties": props, "assumptions_id": aid, "responsible_instructions": sorted({l[1] for l in lits}),
             "applicability": "valid only while these readings are generated by this rule set under the same model assumptions",
             "meaning": "these readings must not remain simultaneously possible"},
            [{"profile": profile_dict(slots, ev), "property": props[0], "trace": t[ev]["results"][props[0]]["trace"]}],
            "all completions of the literals over the enumerated profile space violate a property").to_dict() | {"_cube": cube})
    return out


def _cov(ng, bad):
    return {pr for pr in bad if all(pr[p] == v for p, v in ng["_cube"].items())}


def irredundant_cover(nogoods, V):
    bad, _, _ = bad_safe(V)
    chosen, left = [], set(bad)
    while left:
        best = max(nogoods, key=lambda n: len(_cov(n, bad) & left)); chosen.append(best); left -= _cov(best, bad)
    for ng in list(chosen):
        rest = [c for c in chosen if c is not ng]
        if rest and set().union(*[_cov(c, bad) for c in rest]) >= bad: chosen = rest
    wit = []
    for ng in chosen:
        only = [pr for pr in _cov(ng, bad) if not any(pr in _cov(o, bad) for o in chosen if o is not ng)]
        wit.append({"nogood": ng["id"], "witness_profile": profile_dict(V["slots"], only[0]) if only else None})
    return chosen, wit


# ---------------------------------------------------------------- Feature 6: candidates + optimisation
def candidate_edits(analysis, V, model):
    cands, doms = [], {}
    for (impl, ins), d in V["domains"].items(): doms[ins] = d
    texts = {i.id: i.text for i in analysis["instructions"]}
    for ins, d in doms.items():
        for rid in d:
            rd = reading_lookup(analysis, ins, rid)
            if rd.clarification_text:
                cands.append(ClarificationCandidate(ins, rd.edit_type or "keep-reading", rid, [x for x in d if x != rid], texts[ins], rd.clarification_text, 1,
                                                    len(rd.clarification_text.split()), rd.source_aligned,
                                                    f"keeps only reading '{rid}' of {ins}; removes {[x for x in d if x != rid]} for every implementation").to_dict())
        for rid, txt in model.get("bindings", {}).get(ins, {}).get("exclude_texts", {}).items():
            if rid in d and len(d) > 2:
                cands.append(ClarificationCandidate(ins, "exclude-reading", "!" + rid, [rid], texts[ins], txt, 1, len(txt.split()), False,
                                                    f"removes only reading '{rid}' of {ins}").to_dict())
    return cands


def _hits(chosen, nogoods, slots):
    excl = {c["instruction_id"]: set(c["excludes"]) for c in chosen}
    return {ng["id"] for ng in nogoods if any(v in excl.get(slots[p][1], ()) for p, v in ng["_cube"].items())}


def OPT_META(tried, limit_hit, by):
    space = 1
    for v in by.values(): space *= len(v) + 1
    return {"objective": ["1. hit every nogood (hard constraint; admitted profiles must exclude all violating profiles and be non-empty)", "2. minimise number of edits",
                          "3. minimise permitted-behaviour (safe-profile) loss", "4. minimise total wording length, then number of non-source-aligned edits"],
            "tie_breaking": "tuples compared lexicographically; first-found wins exact ties (deterministic candidate order)",
            "candidate_sets_explored": tried, "search_space_size": space,
            "optimality_proved_within_search_space": not limit_hit}


def optimise(V, nogoods, cands, limits):
    """Exact bounded enumeration. Returns status OPTIMAL / UNSATISFIABLE / INCOMPLETE_LIMIT_REACHED."""
    slots, t = V["slots"], V["table"]
    bad, safe, _ = bad_safe(V)
    by = {}
    for c in cands: by.setdefault(c["instruction_id"], []).append(c)
    instrs = sorted(by); best, tried, limit_hit = None, 0, False
    all_ids = {ng["id"] for ng in nogoods}
    for choice in itertools.product(*[[None] + by[i] for i in instrs]):
        tried += 1
        if tried > limits["max_combos"]: limit_hit = True; break
        chosen = [c for c in choice if c]
        if _hits(chosen, nogoods, slots) != all_ids: continue
        excl = {c["instruction_id"]: set(c["excludes"]) for c in chosen}
        admitted = {pr for pr in t if not any(pr[i] in excl.get(slots[i][1], ()) for i in range(len(slots)))}
        if not admitted or admitted & bad: continue
        key = (len(chosen), len(safe - admitted), sum(c["wording_len"] for c in chosen), sum(0 if c["source_aligned"] else 1 for c in chosen))
        if best is None or key < best[0]: best = (key, chosen, admitted)
    if best is None:
        every = [c for c in cands]
        unhit = sorted(all_ids - _hits(every, nogoods, slots)) if cands else sorted(all_ids)
        return {"status": OPT_LIMIT if limit_hit else OPT_UNSAT, "tried": tried, "best": None, **OPT_META(tried, limit_hit, by),
                "remaining_nogoods": unhit if unhit else sorted(all_ids),
                "reason": ("search limit reached before any valid edit set was found" if limit_hit else
                           ("no candidate edit excludes a literal of these nogoods" if unhit else "no consistent edit combination hits every nogood without emptying the profile space"))}
    key, chosen, admitted = best
    necessity = [{"edit": f"{c['instruction_id']}:{c['keep_reading']}", "nogoods_unsatisfied_without_it": sorted(all_ids - _hits([x for x in chosen if x is not c], nogoods, slots))} for c in chosen]
    return {"status": OPT_LIMIT if limit_hit else OPT_OPTIMAL, "tried": tried, "best": (key, chosen, admitted), "remaining_nogoods": [],
            **OPT_META(tried, limit_hit, by),
            "necessity_witnesses": necessity, "reason": "search limit reached; solution is the best found, not proven optimal" if limit_hit else None}


def _optimise(V, ngs, cands, L):
    if L.get("optimiser") == "maxsat":
        from .maxsat_opt import optimise_maxsat
        return optimise_maxsat(V, ngs, cands, L)
    return optimise(V, ngs, cands, L)


def admitted_by(V_orig, analysis_rev):
    ids = {i: {r.reading_id for r in rs} for i, rs in analysis_rev["readings"].items()}
    return {pr for pr in V_orig["table"] if all(pr[k] in ids.get(s[1], set()) for k, s in enumerate(V_orig["slots"]))}


# ---------------------------------------------------------------- latitude loss (Feature 6 metric)
def behaviour_words(analysis, model, V, profs, limits):
    words, trunc = set(), False
    for pr in profs:
        fsms = build_fsms(model, profile_readings(analysis, model, V["slots"], V["fixed"], pr))
        w, tr = bounded_words(explore(fsms, model["system"], limits["max_states"]), limits["behaviour_depth"], limits["max_words"])
        words |= w; trunc |= tr
    return words, trunc


def loss(before, after):
    """L = |before \\ after| / |before|. Empty baseline is reported explicitly, never as 0."""
    if not before: return {"L": None, "status": "UNDEFINED_EMPTY_BASELINE", "before": 0, "lost": 0}
    lost = len(before - after)
    return {"L": lost / len(before), "status": "DEFINED", "before": len(before), "lost": lost}


def _core(p): return json.dumps({k: v for k, v in p.items() if k not in ("provenance", "span", "instruction", "modality", "description")}, sort_keys=True)


def revised_properties(props_orig, A_rev, A_orig, policy):
    """Property policy for the revised spec. Original properties are ALWAYS held constant (never replaced). Under policy
    'rederive', properties newly derived from the revised text (e.g. an introduced MUST NOT) are checked in addition."""
    orig = {p["id"]: p for p in props_orig}; new, added, changed = [], [], []
    for dp in derived_properties(A_rev):
        prov = dict(dp, provenance={"source": "derived from revised specification", "instruction": dp.get("instruction"), "span": dp.get("span"),
                                      "modality": dp.get("modality"), "spec_version": "revised", "revised_sha256": A_rev["sha256"]})
        if dp["id"] in orig:
            if _core(orig[dp["id"]]) == _core(dp): continue
            changed.append(dp["id"]); new.append(dict(prov, id=dp["id"] + "@revised"))
        else: added.append(dp["id"]); new.append(prov)
    removed = sorted(i for i, p in orig.items() if p.get("provenance", {}).get("source", "").startswith("derived") and i not in {d["id"] for d in derived_properties(A_rev)})
    cmp_ = {"policy": policy, "held_constant": sorted(orig), "added": added, "changed": changed, "removed_in_revised_text": removed,
            "not_checked": [] if policy == "rederive" else sorted(added + changed)}
    return (list(props_orig) + (new if policy == "rederive" else [])), cmp_


def overall_status(analysis, V, restrict=None):
    t = {p: r for p, r in V["table"].items() if restrict is None or p in restrict}
    if any(r["status"] == VIOLATION for r in t.values()): return VIOLATION
    if V["truncated"] or any(s == COV_UNANALYSED for s in analysis["status"].values()) or any(r["status"] == INCOMPLETE for r in t.values()): return INCOMPLETE
    return VERIFIED_SAFE


def coverage_summary(A, V, props):
    cov = {}
    for c in A["coverage"]:
        if c.status in (COV_ANALYSED, COV_SINGLE): cov.setdefault(c.rule_id, set()).add(c.instruction_id)
    per = {}
    for p in props:
        sts = [rec["results"][p["id"]]["status"] for rec in V["table"].values()]
        per[p["id"]] = {"checked_successfully": sts.count(VERIFIED_SAFE), "with_violations": sts.count(VIOLATION), "not_fully_checked": sts.count(INCOMPLETE) + (V["profiles_total"] - V["profiles_checked"])}
    return {"instructions_total": len(A["instructions"]), "instructions_linked_to_model": sum(1 for s in A["status"].values() if s != COV_UNANALYSED or True) and
            sum(1 for i in A["instructions"] if i.id in A.get("_bound", set())) if A.get("_bound") is not None else None,
            "analysed_by_operator": {k: sorted(v) for k, v in cov.items()}, "unresolved_instructions": sorted(i for i, s in A["status"].items() if s == COV_UNANALYSED),
            "properties": per, "profiles_checked": V["profiles_checked"], "profiles_total": V["profiles_total"],
            "limits_reached": {"profile_enumeration": V["truncated"], "state_limit": any(r["complete"] is False for rec in V["table"].values() for r in rec["results"].values())}}


def _edit_log(A0, A1, edits):
    b0, b1 = {i.id: i for i in A0["instructions"]}, {i.id: i for i in A1["instructions"]}
    sp = lambda i: {"line": i.line, "col": i.col, "start": i.start, "end": i.end}
    return [{"instruction_id": e["instruction_id"], "original_wording": e["old_text"], "proposed_wording": e["new_text"],
             "final_wording": b1[e["instruction_id"]].text if e["instruction_id"] in b1 else None, "original_span": sp(b0[e["instruction_id"]]),
             "revised_span": sp(b1[e["instruction_id"]]) if e["instruction_id"] in b1 else None, "edit_type": e["operation"],
             "source_sha256_before": A0["sha256"], "source_sha256_after": A1["sha256"]} for e in edits]


# ---------------------------------------------------------------- full pipeline
def run(spec_text, model, prop_ids=None, mode="compile", limits=None):
    L = dict(DEFAULT_LIMITS, **(limits or {}))
    check_or_raise(model, prop_ids)
    if L["optimiser"] not in ("enumeration", "maxsat"): raise InputError([f"limits.optimiser: unknown optimiser '{L['optimiser']}' (use 'enumeration' or 'maxsat')"])
    if L["optimiser"] == "maxsat":
        from .maxsat_opt import available
        if not available(): raise InputError(["limits.optimiser: 'maxsat' needs the python-sat package (pip install python-sat)"])
    chosen_ids = prop_ids or model.get("default_properties")
    props = [dict(p, provenance={"source": "model", "spec_version": "original"}) for p in model["properties"] if not chosen_ids or p["id"] in chosen_ids]
    A0 = derive_readings(spec_text, model)
    E = validate_readings(A0, model)
    if E: raise InputError(E)
    A0["_bound"] = {i for i in model.get("bindings", {})}
    for dp in derived_properties(A0):
        if dp["id"] not in {p["id"] for p in props}:
            props.append(dict(dp, provenance={"source": "derived from MUST NOT in original specification", "instruction": dp.get("instruction"), "span": dp.get("span"),
                                              "modality": dp.get("modality"), "spec_version": "original", "assumptions": model["system"]["assumptions"]}))
    V0 = verify_all(A0, model, props, L)
    for rs in A0["readings"].values():
        for r in rs: r.check_status = "checked" if not V0["truncated"] else "generated"
    bad0, safe0, inc0 = bad_safe(V0)
    R = {"mode": mode, "limits": L, "properties": props, "spec_sha256": A0["sha256"], "analysis0": A0, "V0": V0,
         "witnesses": witnesses(A0, V0, L), "rounds": [], "status_original": overall_status(A0, V0), "optimisation": None,
         "coverage_summary0": coverage_summary(A0, V0, props)}
    R["coverage_summary0"]["instructions_linked_to_model"] = sum(1 for i in A0["instructions"] if i.id in model.get("bindings", {}))
    if V0["truncated"]:
        R.update(nogoods=[], selected_nogoods=[], irredundancy=[], candidates=[], final_status=INCOMPLETE, revised_text=None, edits=[], A1=A0, V1=V0,
                 unresolved_reason=V0["limit_note"], edit_log=[])
        return R
    R["nogoods"] = derive_nogoods(V0, model, A0) if bad0 else []
    if bad0 and not R["nogoods"]:      # regression: violation independent of any reading choice (e.g. zero reading slots) -> no clarification can remove it
        R.update(selected_nogoods=[], irredundancy=[], candidates=[], revised_text=None, edits=[], A1=A0, V1=V0, edit_log=[], final_status=R["status_original"],
                 optimisation={"status": OPT_UNSAT, "tried": 0, "remaining_nogoods": [], "reason": "violation does not depend on any reading choice; no clarification can remove it", **OPT_META(0, False, {})},
                 unresolved_reason="violation does not depend on any reading choice of the analysed instructions; the model or the properties must be changed, not the wording",
                 revised_properties=list(props), property_comparison={"policy": L["property_policy"], "held_constant": sorted(p["id"] for p in props), "added": [], "changed": [], "removed_in_revised_text": [], "not_checked": []})
        return R
    R["selected_nogoods"], R["irredundancy"] = irredundant_cover(R["nogoods"], V0) if bad0 else ([], [])
    R["candidates"] = candidate_edits(A0, V0, model)
    R["final_status"], R["revised_text"], R["edits"], R["A1"], R["V1"], R["edit_log"] = R["status_original"], None, [], A0, V0, []
    R["revised_properties"], R["property_comparison"] = list(props), {"policy": L["property_policy"], "held_constant": sorted(p["id"] for p in props), "added": [], "changed": [], "removed_in_revised_text": [], "not_checked": []}
    if not bad0: return R
    text, A, V, all_edits = spec_text, A0, V0, []
    for rnd in range(L["max_rounds"]):
        bad, _, _ = bad_safe(V)
        if not bad: break
        ngs = R["nogoods"] if rnd == 0 else derive_nogoods(V, model, A)
        opt = _optimise(V, ngs, candidate_edits(A, V, model), L)
        R["optimisation"] = {k: v for k, v in opt.items() if k != "best"} | {"round": rnd + 1}
        if opt["best"] is None:
            R["final_status"] = CLAR_UNRESOLVED
            R["unresolved_reason"] = f"round {rnd+1}: optimiser {opt['status']}: {opt['reason']}; remaining nogoods {opt['remaining_nogoods']}"; break
        key, chosen, admitted = opt["best"]
        if mode == "audit":
            R["audit_recommendation"] = {"edits": chosen, "objective": key, "optimiser_status": opt["status"], "necessity": opt["necessity_witnesses"]}; return R
        text = apply_edits_to_text(text, chosen); all_edits += chosen
        A = derive_readings(text, model)                 # re-read the REVISED text with the same operators
        A["_bound"] = A0["_bound"]
        E = validate_readings(A, model)
        if E: raise InputError(E)
        props_rev, cmp_ = revised_properties(props, A, A0, L["property_policy"])
        V = verify_all(A, model, props_rev, L)
        R["revised_properties"], R["property_comparison"] = props_rev, cmp_
        R["rounds"].append({"round": rnd + 1, "edits": chosen, "objective": key, "revised_sha256": A["sha256"], "status": overall_status(A, V),
                            "optimiser_status": opt["status"], "necessity": opt["necessity_witnesses"]})
    if mode == "audit": R["final_status"] = R["status_original"]; return R
    R["revised_text"], R["edits"], R["A1"], R["V1"] = text, all_edits, A, V
    R["edit_log"] = _edit_log(A0, A, all_edits) if all_edits else []
    if R["final_status"] != CLAR_UNRESOLVED: R["final_status"] = overall_status(A, V)
    R["coverage_summary1"] = coverage_summary(A, V, R["revised_properties"])
    R["coverage_summary1"]["instructions_linked_to_model"] = sum(1 for i in A["instructions"] if i.id in model.get("bindings", {}))
    adm = admitted_by(V0, A)
    R["admitted_original_profiles"] = sorted(adm)
    R["targeted_violations_remaining"] = sorted(adm & bad0)
    lost = safe0 - adm
    wb, tb = behaviour_words(A0, model, V0, safe0, L)
    _, safe1, _ = bad_safe(V)
    wa, ta = behaviour_words(A, model, V, safe1, L)
    complete = not (tb or ta or V.get("truncated"))
    pl = loss(safe0, safe0 & adm); bw = loss(wb, wa)
    R["latitude"] = {
        "behaviour_definition": "a behaviour is an event word: the ordered sequence of (implementation, action) pairs of one run prefix",
        "universe": "original specification's enumerated profile space under the same model.system assumptions (channels, bounds, state limit)",
        "permitted_before": "profiles verified safe against all selected properties in the original specification; behaviours = event words of those profiles",
        "observation_rules": "identical before and after: same event-word definition, same depth k, same word cap, same state limit, same model.system",
        "profile_level": {"safe_before": len(safe0), "safe_excluded": len(lost), "L": pl["L"], "status": pl["status"]},
        "bounded_behaviour": {"depth": L["behaviour_depth"], "V_before": len(wb), "V_lost": len(wb - wa), "L": bw["L"], "status": bw["status"],
                              "truncated": tb or ta, "word_cap": L["max_words"],
                              "representation": "event words (impl, action) up to depth k over safe profiles; interleavings counted separately"},
        "comparison_status": "COMPLETE_WITHIN_DEPTH" if complete else "INCOMPLETE_TRUNCATED",
        "note": "profile-level and trace-level losses are separate measures; trace-level counts depend on depth k and never cover all executions"}
    pf = {pr for pr in adm if not any(all(pr[p] == v for p, v in ng["_cube"].items()) for ng in R["selected_nogoods"])}
    R["P_F"] = {"size": len(pf), "all_verified_safe": all(V0["table"][p]["status"] == VERIFIED_SAFE for p in pf)}
    return R
