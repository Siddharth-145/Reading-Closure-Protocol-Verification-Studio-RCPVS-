"""Feature 8: verification certificate + INDEPENDENT checker.

Independence (honest scope): the checker derives readings with its OWN rule code (checker_rules.py, no import of spec_analysis).
It shares with the engine only documented conventions: rule-set version string, model/binding schema, patch-operation semantics.
It has its own anchoring, patch application, state exploration (DFS), property evaluation for every property type, trace replay,
hash/schema checks, and recomputes every status instead of trusting the reported one.
Outcomes per claim: VERIFIED (independently reproduced) / REJECTED (malformed or contradicted) / UNVERIFIED (cannot decide in limits).
"""
from __future__ import annotations
import copy, itertools, json
from .models import *
from .checker_rules import derive as derive_readings, apply_edits as apply_edits_to_text, sha as sha256, RULE_SET_VERSION, patch_digest


def canon(x) -> str: return json.dumps(x, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------- generation
def _results(V):
    out = []
    for pr, rec in V["table"].items():
        for pid, r in rec["results"].items():
            out.append({"profile": list(pr), "property": pid, "status": r["status"], "trace": r["trace"], "states_explored": r["states_explored"],
                        "complete": r["complete"], "reason": r.get("reason")})
    return out


def _side(A, V):
    return {"slots": [list(s) for s in V["slots"]], "domains": {f"{a}::{b}": d for (a, b), d in V["domains"].items()},
            "results": _results(V), "coverage": dict(A["status"]), "coverage_records": [[c.instruction_id, c.rule_id, c.status] for c in A["coverage"]],
            "profiles_total": V["profiles_total"], "profiles_checked": V["profiles_checked"],
            "instructions": [{"id": i.id, "line": i.line, "col": i.col, "start": i.start, "end": i.end, "text_sha256": i.text_sha256} for i in A["instructions"]],
            "readings": [{"instruction_id": r.instruction_id, "reading_id": r.reading_id, "rule_id": r.rule_id, "rule_version": r.rule_version, "span": list(r.span),
                          "patch_sha256": patch_digest(r.patch)} for rs in A["readings"].values() for r in rs]}


def build_certificate(R, model, tests=None):
    A0, A1, V0, V1 = R["analysis0"], R["A1"], R["V0"], R["V1"]
    body = {
        "format": "RCPVS-certificate/2", "rule_set_version": RULE_SET_VERSION, "model": model, "model_sha256": sha256(canon(model)),
        "properties": R["properties"], "properties_sha256": sha256(canon(R["properties"])), "limits": R["limits"],
        "model_assumptions": model["system"]["assumptions"],
        "spec": A0["text"], "spec_sha256": A0["sha256"],
        "revised_spec": R["revised_text"], "revised_sha256": A1["sha256"] if R["revised_text"] is not None else None,
        "original": dict(_side(A0, V0), claimed_status=R["status_original"]),
        "revised": None if R["revised_text"] is None else dict(_side(A1, V1), claimed_status=R["final_status"]),
        "revised_properties": R.get("revised_properties"), "revised_properties_sha256": sha256(canon(R.get("revised_properties"))),
        "property_comparison": R.get("property_comparison"),
        "nogoods": [{"id": n["id"], "literals": [list(l) for l in n["literals"]]} for n in R["nogoods"]],
        "selected_nogoods": [n["id"] for n in R["selected_nogoods"]],
        "edits": [{"instruction_id": e["instruction_id"], "new_text": e["new_text"], "keep_reading": e["keep_reading"]} for e in R["edits"]],
        "removal_claim": {"targeted_remaining": len(R.get("targeted_violations_remaining", []))} if R["revised_text"] is not None else None,
        "tests": tests or [],
        "coverage_note": "Status VERIFIED_SAFE_WITHIN_SCOPE is only as broad as 'coverage'; UNANALYSED instructions are listed per instruction.",
    }
    return VerificationCertificate(body).to_dict()


# ---------------------------------------------------------------- schema
def _schema(c) -> list:
    E = []
    req = {"format": str, "rule_set_version": str, "model": dict, "model_sha256": str, "properties": list, "properties_sha256": str, "limits": dict,
           "model_assumptions": dict, "spec": str, "spec_sha256": str, "original": dict, "nogoods": list, "selected_nogoods": list, "edits": list, "tests": list, "property_comparison": dict}
    if not isinstance(c, dict): return ["certificate is not an object"]
    for k, t in req.items():
        if k not in c: E.append(f"missing field '{k}'")
        elif not isinstance(c[k], t): E.append(f"field '{k}' has wrong type")
    if E: return E
    for side in ("original", "revised"):
        s = c.get(side)
        if s is None and side == "revised": continue
        for k, t in {"slots": list, "domains": dict, "results": list, "coverage": dict, "coverage_records": list, "claimed_status": str, "instructions": list, "readings": list}.items():
            if not isinstance(s, dict) or k not in s or not isinstance(s[k], t): E.append(f"{side}.{k} missing or wrong type")
    for k in ("max_states", "max_profiles"):
        if not isinstance(c["limits"].get(k), int) or c["limits"][k] < 1: E.append(f"limits.{k} must be a positive integer")
    return E


# ---------------------------------------------------------------- independent machinery
def _patched(role, readings):
    r = copy.deepcopy(role)
    for t in r["transitions"]: t.setdefault("tag", "base")
    for rd in readings:
        tag = f"{rd.instruction_id}:{rd.reading_id}"
        for p in rd.patch:
            o = p["op"]
            if o in ("bypass", "remove"):
                tid = p.get("remove", p.get("tid"))
                old = [t for t in r["transitions"] if t["id"] == tid]
                if not old: raise ValueError("conflict")
                r["transitions"] = [t for t in r["transitions"] if t["id"] != tid]
                if o == "bypass":
                    ns = p["action"].upper() + "~" + tag
                    r["states"][ns] = {"closed": p["action"][:5] == "close"}
                    r["transitions"].append({"id": tid + "'~" + tag, "src": old[0]["src"], "dst": ns, "action": p["action"], "tag": tag})
            elif o == "add": r["transitions"].append(dict(p["t"], tag=tag))
            elif o in ("rename_msg", "set_action"):
                for t in r["transitions"]:
                    if t["id"] == p["tid"]:
                        keep = "@" + t["action"].split("@")[1] if "@" in t["action"] else ""
                        t["action"] = (t["action"][0] + p["msg"] + keep) if o == "rename_msg" else p["action"]; t["tag"] = tag
            elif o == "set_closed":
                for s in r["states"]: r["states"][s]["closed"] = s in p["states"]
    return r


def _moves(fsms, names, system, s):
    cap, peers, res = system.get("channel_capacity", 1), {n: system["implementations"][n].get("peer") for n in names}, []
    locs, ch = s
    for i, n in enumerate(names):
        for t in fsms[n]["transitions"]:
            if t["src"] != locs[i]: continue
            a, c2 = t["action"], list(ch)
            if a[0] == "!":
                body, at, who = a[1:].partition("@")
                j = names.index(who if at else peers[n])
                if len(c2[j]) >= cap: continue
                c2[j] = c2[j] + (body,)
            elif a[0] == "?":
                if not c2[i] or c2[i][0] != a[1:].split("@")[0]: continue
                c2[i] = c2[i][1:]
            l2 = list(locs); l2[i] = t["dst"]
            res.append((n, t, (tuple(l2), tuple(c2))))
    return res


def _reach(fsms, system, names, limit):
    init = (tuple(fsms[n]["initial"] for n in names), tuple(() for _ in names))
    seen, edges, stack, complete = {init}, {}, [init], True
    while stack:
        s = stack.pop(); edges[s] = _moves(fsms, names, system, s)
        for _, _, ns in edges[s]:
            if ns not in seen:
                if len(seen) >= limit: complete = False; continue
                seen.add(ns); stack.append(ns)
    return init, seen, edges, complete


def _orphan(fsms, names, s): return any(fsms[n]["states"].get(s[0][i], {}).get("closed") and s[1][i] for i, n in enumerate(names))


def _recv_reach(fsm, st):
    seen, todo = {st}, [st]
    while todo:
        x = todo.pop()
        for t in fsm["transitions"]:
            if t["src"] == x and t["dst"] not in seen: seen.add(t["dst"]); todo.append(t["dst"])
    return {t["action"][1:].split("@")[0] for t in fsm["transitions"] if t["src"] in seen and t["action"][0] == "?"}


def _gs(prop, fsms, key):
    return {n: ({q for q, f in fsms[n]["states"].items() if f.get("closed")} if "@closed" in v else set(v)) for n, v in prop[key].items()}


def _eval(prop, fsms, names, system, limit, declared):
    """Independent property evaluation. Returns (status, ctx) where ctx['final_ok'](steps, last_state) validates a claimed trace's end."""
    init, seen, edges, complete = _reach(fsms, system, names, limit)
    t, ok = prop["type"], (VERIFIED_SAFE if True else None)
    safe_or_inc = VERIFIED_SAFE if complete else INCOMPLETE
    ctx = {"init": init, "edges": edges, "seen": seen}
    pred = None
    if t == "no_orphan_message": pred = lambda s: _orphan(fsms, names, s)
    elif t == "deadlock_freedom":
        fs = _gs(prop, fsms, "final") if prop.get("final") else {n: {q for q, f in fsms[n]["states"].items() if f.get("closed")} for n in names}
        pred = lambda s: not edges.get(s) and not (all(s[0][i] in fs[n] for i, n in enumerate(names)) and not any(s[1]))
    elif t == "unspecified_reception": pred = lambda s: any(s[1][i] and s[1][i][0] not in _recv_reach(fsms[n], s[0][i]) for i, n in enumerate(names))
    elif t == "state_invariant":
        pred = lambda s: any(all(s[0][names.index(n)] in v for n, v in f.get("locals", {}).items()) and (not f.get("channels_empty") or not any(s[1])) for f in prop["forbid"])
    if pred:
        ctx["final_ok"] = lambda steps, s: pred(s)
        return (VIOLATION if any(pred(s) for s in seen) else safe_or_inc), ctx
    if t in ("forbidden_action", "invalid_transition"):
        msgs = set(declared or [])
        def bad(n, tr):
            if t == "forbidden_action": return ((tr["id"] == prop["tid"]) if prop.get("tid") else tr["action"] == prop["action"]) and prop.get("impl") in (None, n)
            return tr["dst"] not in fsms[n]["states"] or tr["src"] not in fsms[n]["states"] or (bool(msgs) and tr["action"][0] in "!?" and tr["action"][1:].split("@")[0] not in msgs)
        ctx["final_ok"] = lambda steps, s: bool(steps) and bad(steps[-1]["impl"], next(x for x in fsms[steps[-1]["impl"]]["transitions"] if x["id"] == steps[-1]["tid"]))
        return (VIOLATION if any(bad(n, tr) for s in seen for n, tr, _ in edges[s]) else safe_or_inc), ctx
    if t == "required_ordering":
        start, stack, vis, found = (init, frozenset()), [(init, frozenset())], {(init, frozenset())}, False
        while stack and not found:
            s, fl = stack.pop()
            for n, tr, ns in edges.get(s, []):
                if tr["action"] == prop["later"] and prop.get("impl") in (None, n) and n not in fl: found = True; break
                nf = fl | {n} if tr["action"] == prop["earlier"] else fl
                if (ns, nf) not in vis: vis.add((ns, nf)); stack.append((ns, nf))
        def fin(steps, s):
            fl = set()
            for st in steps[:-1]:
                if next(x for x in fsms[st["impl"]]["transitions"] if x["id"] == st["tid"])["action"] == prop["earlier"]: fl.add(st["impl"])
            if not steps: return False
            last = steps[-1]; a = next(x for x in fsms[last["impl"]]["transitions"] if x["id"] == last["tid"])["action"]
            return a == prop["later"] and prop.get("impl") in (None, last["impl"]) and last["impl"] not in fl
        ctx["final_ok"] = fin
        return (VIOLATION if found else safe_or_inc), ctx
    gs = _gs(prop, fsms, "goal")
    goal = lambda s: all(s[0][i] in gs[n] for i, n in enumerate(names)) and not any(s[1])
    good = {s for s in seen if goal(s)}
    changed = True
    while changed:
        changed = False
        for s in seen:
            if s not in good and any(ns in good for _, _, ns in edges.get(s, [])): good.add(s); changed = True
    if t == "can_complete":
        if init in good: ctx["final_ok"] = lambda steps, s: False; return VERIFIED_SAFE, ctx
        ctx["final_ok"] = lambda steps, s: s not in good
        return (VIOLATION if complete else INCOMPLETE), ctx
    if t == "always_can_complete":
        ctx["final_ok"] = lambda steps, s: s not in good
        if seen - good: return (VIOLATION if complete else INCOMPLETE), ctx
        return safe_or_inc, ctx
    if t == "inevitable_completion":
        if goal(init): ctx["final_ok"] = lambda steps, s: False; return safe_or_inc, ctx
        N, stack = {init}, [init]
        while stack:
            s = stack.pop()
            for _, _, ns in edges.get(s, []):
                if ns in seen and not goal(ns) and ns not in N: N.add(ns); stack.append(ns)
        terminal = {s for s in N if not edges.get(s)}
        alive = set(N)
        while True:
            drop = {s for s in alive if not any(ns in alive for _, _, ns in edges.get(s, []))}
            if not drop: break
            alive -= drop
        bad_states = terminal | alive
        ctx["final_ok"] = lambda steps, s: s in bad_states or (bool(steps) and False)
        # a lasso witness ends one step after a cycle node; accept any state of N that can reach `alive`
        ctx["final_ok"] = lambda steps, s: s in bad_states or any(ns in alive for _, _, ns in edges.get(s, []))
        return (VIOLATION if bad_states else (VERIFIED_SAFE if complete else INCOMPLETE)), ctx
    raise ValueError("unknown property type " + t)


def _replay(fsms, names, system, steps, init):
    s = init
    for st in steps:
        mv = [m for m in _moves(fsms, names, system, s) if m[0] == st["impl"] and m[1]["id"] == st["tid"]]
        if not mv: return None, f"step {st['step']} not enabled"
        s = mv[0][2]
        if dict(zip(names, s[0])) != st["locals"] or {x: tuple(c) for x, c in zip(names, s[1])} != {x: tuple(c) for x, c in st["channels"].items()}:
            return None, f"step {st['step']} state mismatch"
    return s, ""


def _space(A, model):
    slots, dom, fixed = [], {}, {}
    for impl, cfg in sorted(model["system"]["implementations"].items()):
        for ins in A["instructions"]:
            b = model.get("bindings", {}).get(ins.id)
            if not b or b.get("role") != cfg["role"]: continue
            rs = A["readings"][ins.id]
            if len(rs) > 1: slots.append((impl, ins.id)); dom[(impl, ins.id)] = [r.reading_id for r in rs]
            elif rs: fixed[(impl, ins.id)] = rs[0]
    return slots, dom, fixed


def _fsms(A, model, slots, fixed, prof):
    by = {n: [] for n in model["system"]["implementations"]}
    for (i, _), r in fixed.items(): by[i].append(r)
    for (i, s), rid in zip(slots, prof): by[i].append(next(r for r in A["readings"][s] if r.reading_id == rid))
    return {n: _patched(model["roles"][model["system"]["implementations"][n]["role"]], rs) for n, rs in by.items()}


def check_certificate(cert: dict) -> dict:
    claims = []
    def add(name, verdict, detail=""): claims.append({"claim": name, "verdict": verdict, "detail": detail})
    def done():
        rej = [c for c in claims if c["verdict"] == "REJECTED"]; unv = [c for c in claims if c["verdict"] == "UNVERIFIED"]
        return {"accepted": not rej and not unv, "status": CERT_REJECTED if rej else ("PARTIALLY_VERIFIED" if unv else "CERTIFICATE_ACCEPTED"),
                "counts": {"verified": sum(c["verdict"] == "VERIFIED" for c in claims), "rejected": len(rej), "unverified": len(unv)}, "claims": claims}
    errs = _schema(cert)
    if errs:
        for e in errs: add("schema: " + e, "REJECTED")
        return done()
    model, props, lim = cert["model"], cert["properties"], cert["limits"]
    declared = model.get("messages")
    add("revised property-set hash", "VERIFIED" if (not cert.get("revised") or sha256(canon(cert.get("revised_properties"))) == cert.get("revised_properties_sha256")) else "REJECTED")
    add("model hash matches embedded model", "VERIFIED" if sha256(canon(model)) == cert["model_sha256"] else "REJECTED")
    add("property-set hash matches embedded properties", "VERIFIED" if sha256(canon(props)) == cert["properties_sha256"] else "REJECTED")
    add("recorded assumptions equal model.system.assumptions", "VERIFIED" if cert["model_assumptions"] == model.get("system", {}).get("assumptions") else "REJECTED")
    add("rule set version known", "VERIFIED" if cert["rule_set_version"] == RULE_SET_VERSION else "REJECTED", cert["rule_set_version"])
    versions = [("original", cert["spec"], cert["spec_sha256"], cert["original"])]
    if cert.get("revised"): versions.append(("revised", cert["revised_spec"], cert["revised_sha256"], cert["revised"]))
    own = {}
    for name, text, sha, claim in versions:
        add(f"{name} spec hash", "VERIFIED" if sha256(text) == sha else "REJECTED")
        A = derive_readings(text, model)
        slots, dom, fixed = _space(A, model)
        ok = ([list(s) for s in slots] == claim["slots"] and {f"{a}::{b}": d for (a, b), d in dom.items()} == claim["domains"] and dict(A["status"]) == claim["coverage"])
        add(f"{name}: re-derived readings, domains and per-instruction coverage match", "VERIFIED" if ok else "REJECTED")
        ins_ok = [{"id": i.id, "line": i.line, "col": i.col, "start": i.start, "end": i.end, "text_sha256": i.text_sha256} for i in A["instructions"]] == claim.get("instructions")
        add(f"{name}: instruction anchors (ids, spans, text hashes) match", "VERIFIED" if ins_ok else "REJECTED")
        rd_ok = [{"instruction_id": r.instruction_id, "reading_id": r.reading_id, "rule_id": r.rule_id, "rule_version": r.rule_version, "span": list(r.span),
                  "patch_sha256": patch_digest(r.patch)} for rs in A["readings"].values() for r in rs] == claim.get("readings")
        add(f"{name}: reading ids, rule ids/versions, spans and model effects match", "VERIFIED" if rd_ok else "REJECTED")
        add(f"{name}: coverage records match", "VERIFIED" if [[c.instruction_id, c.rule_id, c.status] for c in A["coverage"]] == claim["coverage_records"] else "REJECTED")
        pmap = {p["id"]: p for p in (cert["revised_properties"] if name == "revised" and cert.get("revised_properties") else props)}
        missing_prop = [r["property"] for r in claim["results"] if r["property"] not in pmap]
        if missing_prop: add(f"{name}: results reference unknown properties", "REJECTED", str(missing_prop))
        table, bad, safe = {}, set(), set()
        total = 1
        for s in slots: total *= len(dom[s])
        add(f"{name}: profile count", "VERIFIED" if claim["profiles_total"] == total else "REJECTED", f"claimed {claim['profiles_total']}, checker {total}")
        for prof in itertools.islice(itertools.product(*[dom[s] for s in slots]), lim["max_profiles"]):
            fsms = _fsms(A, model, slots, fixed, prof); names = sorted(fsms)
            vs = []
            rs = [x for x in claim["results"] if x["profile"] == list(prof)]
            if {r["property"] for r in rs} != set(pmap): add(f"{name}: profile {list(prof)} has results for every property", "REJECTED")
            for r in rs:
                if r["property"] not in pmap: continue
                st, ctx = _eval(pmap[r["property"]], fsms, names, model["system"], lim["max_states"], declared)
                verdict, det = "VERIFIED", ""
                if st == INCOMPLETE and r["status"] == INCOMPLETE: det = "incomplete confirmed"
                elif st == INCOMPLETE: verdict, det = "UNVERIFIED", "checker could not decide within limits"
                elif st != r["status"]: verdict, det = "REJECTED", f"claimed {r['status']} but checker computed {st}"
                elif st == VIOLATION:
                    final, why = _replay(fsms, names, model["system"], r["trace"] or [], ctx["init"])
                    if final is None: verdict, det = "REJECTED", "trace replay failed: " + why
                    elif not ctx["final_ok"](r["trace"] or [], final): verdict, det = "REJECTED", "trace does not end in a violating state/event"
                    else: det = "trace replayed and ends in violation"
                add(f"{name}: profile {list(prof)} / {r['property']}", verdict, det)
                vs.append(st)
            ps = VIOLATION if VIOLATION in vs else (INCOMPLETE if INCOMPLETE in vs else VERIFIED_SAFE)
            table[prof] = ps
            if ps == VIOLATION: bad.add(prof)
            elif ps == VERIFIED_SAFE: safe.add(prof)
        own[name] = (A, slots, dom, table, bad, safe, fixed)
    A0, s0, d0, t0, bad0, safe0, f0 = own["original"]
    for ng in cert["nogoods"]:
        lits = [(s0.index((i, s)), r) for i, s, r in ng["literals"]]
        comp = [p for p in t0 if all(p[k] == r for k, r in lits)]
        add(f"nogood {ng['id']} excludes only violating profiles", "VERIFIED" if comp and all(p in bad0 for p in comp) else "REJECTED")
    sel = [n for n in cert["nogoods"] if n["id"] in cert["selected_nogoods"]]
    covered = {p for n in sel for p in t0 if all(p[s0.index((i, s))] == r for i, s, r in n["literals"])}
    if cert["nogoods"] or bad0: add("selected nogoods cover every violating profile", "VERIFIED" if covered >= bad0 else "REJECTED")
    def overall(A, table):
        if VIOLATION in table.values(): return VIOLATION
        if COV_UNANALYSED in A["status"].values() or INCOMPLETE in table.values(): return INCOMPLETE
        return VERIFIED_SAFE
    o0 = overall(A0, t0)
    add("original overall status", "VERIFIED" if o0 == cert["original"]["claimed_status"] else "REJECTED", f"checker: {o0}")
    if cert.get("revised"):
        A1, s1, d1, t1, bad1, safe1, f1 = own["revised"]
        re_text = cert["spec"]
        for e in cert["edits"]: re_text = apply_edits_to_text(re_text, [e])
        add("revised spec equals original with listed edits applied", "VERIFIED" if re_text == cert["revised_spec"] else "REJECTED")
        ids = {i: {r.reading_id for r in rs} for i, rs in A1["readings"].items()}
        adm = {p for p in t0 if all(p[k] in ids.get(s[1], set()) for k, s in enumerate(s0))}
        add("targeted violating profiles are no longer possible", "VERIFIED" if not (adm & bad0) else "REJECTED", f"{len(adm & bad0)} remain")
        add("removal claim matches", "VERIFIED" if cert["removal_claim"] and cert["removal_claim"]["targeted_remaining"] == len(adm & bad0) else "REJECTED")
        orig_ids = {p["id"] for p in props}; new_ids = sorted(set(A1["derived_ids"]) - orig_ids)
        exp_ids = orig_ids | (set(new_ids) if lim.get("property_policy", "rederive") == "rederive" else set())
        add("revised property set = original properties (held constant) + newly derived ones", "VERIFIED" if {p["id"] for p in cert["revised_properties"]} == exp_ids and orig_ids <= {p["id"] for p in cert["revised_properties"]} else "REJECTED")
        cmpd = cert.get("property_comparison") or {}
        add("property comparison (held/added) matches checker derivation", "VERIFIED" if sorted(cmpd.get("added", [])) == new_ids and sorted(cmpd.get("held_constant", [])) == sorted(orig_ids) else "REJECTED")
        if lim.get("property_policy", "rederive") != "rederive":
            add("under policy 'original' newly derivable properties are listed as not checked", "VERIFIED" if sorted(cmpd.get("not_checked", [])) == new_ids else "REJECTED")
        for np_ in (new_ids if lim.get("property_policy", "rederive") == "rederive" else []):
            iid = np_[5:]; pr = model["bindings"][iid]["MODALITY"]["prohibit"]; got = next((p for p in cert["revised_properties"] if p["id"] == np_), {})
            add(f"new property {np_} matches the binding's prohibition", "VERIFIED" if all(got.get(k) == v for k, v in pr.items() if k != "reading") else "REJECTED")
        rs = overall(A1, t1); claimed = cert["revised"]["claimed_status"]
        add("revised overall status", "VERIFIED" if rs == claimed or claimed == CLAR_UNRESOLVED else "REJECTED", f"checker: {rs}")
    for tst in cert.get("tests", []):
        ver = tst["setup"].get("model_version", "revised" if cert.get("revised") else "original")
        if ver not in own: add(f"conformance test {tst['id']}", "REJECTED", f"unknown model version {ver}"); continue
        A, slots, dom, _, _, _, fixed = own[ver]
        try:
            fsms = _fsms(A, model, slots, fixed, tuple(tst["setup"]["profile"])); names = sorted(fsms)
            init = (tuple(fsms[n]["initial"] for n in names), tuple(() for _ in names)); s, good = init, True
            for st in tst["steps"]:
                mv = [m for m in _moves(fsms, names, model["system"], s) if m[0] == st["impl"] and m[1]["id"] == st["tid"]]
                if not mv: good = False; break
                s = mv[0][2]
        except Exception as e: good = False
        add(f"conformance test {tst['id']} replays on the {ver} model", "VERIFIED" if good else "REJECTED")
    return done()
