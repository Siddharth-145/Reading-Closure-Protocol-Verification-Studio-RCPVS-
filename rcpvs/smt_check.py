"""Third verification path (Priority 3): SMT bounded model checking with Z3.

Chain used here: checker_rules.derive (own rule code) -> certificate._patched/_fsms (own patching) -> Z3 encoding of the documented
composition semantics (docs/SEMANTICS.md). It does NOT use the engine's operators, patching or explicit-state exploration.
Scope: it cross-checks properties that are decidable by bounded reachability: no_orphan_message, forbidden_action, state_invariant,
deadlock_freedom, unspecified_reception, can_complete. always_can_complete / inevitable_completion / required_ordering are
UNSUPPORTED here (they need liveness or history); this is reported, never silently skipped.
A 'no violation within k steps' answer equals the engine's complete SAFE answer only if k >= the reachable-state diameter; the
result states k explicitly. Same author as the engine: this is a different METHOD, not an independent human review."""
from __future__ import annotations
import itertools
import z3
from .checker_rules import derive as ck_derive
from .certificate import _space, _fsms
from .models import VIOLATION, VERIFIED_SAFE, INCOMPLETE

SUPPORTED = {"no_orphan_message", "forbidden_action", "state_invariant", "deadlock_freedom", "unspecified_reception", "can_complete"}


def _recv_reach(fsm, st):
    seen, todo = {st}, [st]
    while todo:
        x = todo.pop()
        for t in fsm["transitions"]:
            if t["src"] == x and t["dst"] not in seen: seen.add(t["dst"]); todo.append(t["dst"])
    return {t["action"][1:].split("@")[0] for t in fsm["transitions"] if t["src"] in seen and t["action"][0] == "?"}


def check_profile(fsms, system, prop, declared, k):
    """Returns {'status', 'depth'}; status in VIOLATION / NO_VIOLATION_WITHIN_BOUND / GOAL_REACHED / GOAL_NOT_REACHED_WITHIN_BOUND / UNSUPPORTED."""
    if prop["type"] not in SUPPORTED: return {"status": "UNSUPPORTED", "depth": None}
    names = sorted(fsms); N = len(names); cap = system.get("channel_capacity", 1); peers = {n: system["implementations"][n].get("peer") for n in names}
    sid = [{s: i for i, s in enumerate(sorted(fsms[n]["states"]))} for n in names]
    msgs = sorted({t["action"][1:].split("@")[0] for n in names for t in fsms[n]["transitions"] if t["action"][0] in "!?"}); mid = {m: i for i, m in enumerate(msgs)}
    G = [(i, t) for i, n in enumerate(names) for t in fsms[n]["transitions"]]
    L = lambda i, t: z3.Int(f"L_{i}_{t}"); Q = lambda j, t: z3.Int(f"n_{j}_{t}"); M = lambda j, t, c: z3.Int(f"q_{j}_{t}_{c}")
    s = z3.Solver()
    for i in range(N): s.add(L(i, 0) == sid[i][fsms[names[i]]["initial"]])
    for j in range(N):
        s.add(Q(j, 0) == 0)
        for c in range(cap): s.add(M(j, 0, c) == -1)
    def tgt(i, a): return names.index(a[1:].partition("@")[2]) if "@" in a else names.index(peers[names[i]])
    def guard(g, t):
        i, tr = G[g]; a = tr["action"]; c = [L(i, t) == sid[i][tr["src"]]]
        if a[0] == "!": c.append(Q(tgt(i, a), t) < cap)
        elif a[0] == "?": c += [Q(i, t) > 0, M(i, t, 0) == mid[a[1:].split("@")[0]]]
        return z3.And(*c)
    def effect(g, t):
        i, tr = G[g]; a = tr["action"]; c = [L(i, t + 1) == sid[i][tr["dst"]]] + [L(m, t + 1) == L(m, t) for m in range(N) if m != i]
        touched = None
        if a[0] == "!":
            j = tgt(i, a); touched = j; msg = mid[a[1:].partition("@")[0]]
            c.append(Q(j, t + 1) == Q(j, t) + 1)
            for q in range(cap): c.append(M(j, t + 1, q) == z3.If(q < Q(j, t), M(j, t, q), z3.If(q == Q(j, t), msg, -1)))
        elif a[0] == "?":
            touched = i; c.append(Q(i, t + 1) == Q(i, t) - 1)
            for q in range(cap): c.append(M(i, t + 1, q) == (M(i, t, q + 1) if q + 1 < cap else -1))
        for j in range(N):
            if j != touched:
                c.append(Q(j, t + 1) == Q(j, t)); c += [M(j, t + 1, q) == M(j, t, q) for q in range(cap)]
        return z3.And(*c)
    closed = [[sid[i][x] for x, f in fsms[names[i]]["states"].items() if f.get("closed")] for i in range(N)]
    def in_(v, ids): return z3.Or(*[v == x for x in ids]) if ids else z3.BoolVal(False)
    def goalset(key, i): return [sid[i][x] for x in (closed_names(i) if "@closed" in prop[key][names[i]] else prop[key][names[i]])]
    def closed_names(i): return [x for x, f in fsms[names[i]]["states"].items() if f.get("closed")]
    def bad(d, fired):
        tp = prop["type"]
        if tp == "no_orphan_message": return z3.Or(*[z3.And(in_(L(i, d), closed[i]), Q(i, d) > 0) for i in range(N)])
        if tp == "state_invariant":
            alts = []
            for f in prop["forbid"]:
                c = [in_(L(names.index(n), d), [sid[names.index(n)][x] for x in v if x in sid[names.index(n)]]) for n, v in f.get("locals", {}).items()]
                if f.get("channels_empty"): c += [Q(j, d) == 0 for j in range(N)]
                alts.append(z3.And(*c))
            return z3.Or(*alts)
        if tp == "forbidden_action":
            hit = [fired[g] for g, (i, tr) in enumerate(G) if ((tr["id"] == prop["tid"]) if prop.get("tid") else tr["action"] == prop["action"]) and prop.get("impl") in (None, names[i])]
            return z3.Or(*hit) if hit and d > 0 else z3.BoolVal(False)
        if tp == "deadlock_freedom":
            fin = {i: (goalset("final", i) if prop.get("final") else [sid[i][x] for x in closed_names(i)]) for i in range(N)}
            final = z3.And(*[in_(L(i, d), fin[i]) for i in range(N)], *[Q(j, d) == 0 for j in range(N)])
            return z3.And(*[z3.Not(guard(g, d)) for g in range(len(G))], z3.Not(final))
        if tp == "unspecified_reception":
            alts = []
            for i in range(N):
                for st, v in sid[i].items():
                    ok = _recv_reach(fsms[names[i]], st)
                    for m, mi in mid.items():
                        if m not in ok: alts.append(z3.And(L(i, d) == v, Q(i, d) > 0, M(i, d, 0) == mi))
            return z3.Or(*alts) if alts else z3.BoolVal(False)
        if tp == "can_complete":
            return z3.And(*[in_(L(i, d), goalset("goal", i)) for i in range(N)], *[Q(j, d) == 0 for j in range(N)])
    fired_all = []
    for d in range(k + 1):
        fired = fired_all[-1] if fired_all else None
        s.push(); s.add(bad(d, fired or [z3.BoolVal(False)] * len(G)))
        if s.check() == z3.sat:
            s.pop()
            return {"status": ("GOAL_REACHED" if prop["type"] == "can_complete" else VIOLATION), "depth": d}
        s.pop()
        if d == k: break
        f = [z3.Bool(f"f_{d}_{g}") for g in range(len(G))]; fired_all.append(f)
        s.add(z3.Or(*f)) if G else s.add(z3.BoolVal(False))
        for g in range(len(G)): s.add(z3.Implies(f[g], z3.And(guard(g, d), effect(g, d))))
        if s.check() != z3.sat: break                 # no path of this length: nothing deeper is reachable
    return {"status": "GOAL_NOT_REACHED_WITHIN_BOUND" if prop["type"] == "can_complete" else "NO_VIOLATION_WITHIN_BOUND", "depth": None}


def crosscheck(R, model, k=24):
    """Compare every engine verdict (original and revised sides) with the SMT verdict. Returns a summary with all disagreements."""
    out = {"k": k, "compared": 0, "agree": 0, "disagree": [], "unsupported": 0, "skipped_incomplete": 0, "by_type": {}}
    sides = [("original", R["analysis0"]["text"], R["V0"], R["properties"])]
    if R.get("revised_text") is not None: sides.append(("revised", R["revised_text"], R["V1"], R["revised_properties"]))
    for name, text, V, props in sides:
        A = ck_derive(text, model); slots, dom, fixed = _space(A, model)
        for prof, rec in V["table"].items():
            fs = _fsms(A, model, slots, fixed, prof)
            for p in props:
                eng = rec["results"][p["id"]]; tp = p["type"]
                if tp not in SUPPORTED: out["unsupported"] += 1; out["by_type"].setdefault(tp, "UNSUPPORTED"); continue
                if eng["status"] == INCOMPLETE: out["skipped_incomplete"] += 1; continue
                smt = check_profile(fs, model["system"], p, model.get("messages"), k)
                out["compared"] += 1; out["by_type"][tp] = "compared"
                if tp == "can_complete": ok = (eng["status"] == VERIFIED_SAFE) == (smt["status"] == "GOAL_REACHED")
                elif eng["status"] == VIOLATION: ok = smt["status"] == VIOLATION and smt["depth"] == len(eng["trace"])      # BFS shortest witness length must match
                else: ok = smt["status"] == "NO_VIOLATION_WITHIN_BOUND"
                if ok: out["agree"] += 1
                else: out["disagree"].append({"side": name, "profile": list(prof), "property": p["id"], "engine": eng["status"], "engine_depth": len(eng["trace"] or []), "smt": smt})
    return out
