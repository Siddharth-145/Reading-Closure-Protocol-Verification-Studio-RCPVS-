"""Optional weighted-MaxSAT clarification optimiser (limits['optimiser'] == 'maxsat'), solved with RC2 from python-sat.

Encoding (same lexicographic objective as the enumeration optimiser, folded into weights):
  x_e   : edit candidate e is selected
  y_p   : safe profile p is lost (some selected edit excludes one of its readings)
  a_q   : profile q is still admitted (no selected edit excludes any of its readings)
Hard:  at most one edit per instruction; every conditional nogood is hit by >=1 selected edit; x_e -> y_p for every safe p that e excludes;
       a_q -> not x_e for every e excluding q; at least one a_q (the admitted space is non-empty).
Soft:  not x_e with weight u1 + u3*wording_len(e) + u4*[e not source-aligned];  not y_p with weight u2.
Weights are chosen so that  #edits  >>  #lost safe profiles  >>  total wording  >>  #non-aligned  (strictly lexicographic).
Exact ties between equally good edit sets are broken by the solver, not by candidate order."""
from __future__ import annotations
import itertools
from .models import OPT_OPTIMAL, OPT_UNSAT


def available():
    try:
        import pysat.examples.rc2  # noqa
        return True
    except ImportError:
        return False


def optimise_maxsat(V, nogoods, cands, limits):
    from pysat.formula import WCNF
    from pysat.examples.rc2 import RC2
    from .engine import _hits, bad_safe, OPT_META
    slots, table = V["slots"], V["table"]
    bad, safe, _ = bad_safe(V)
    cands = sorted(cands, key=lambda c: (c["instruction_id"], c["keep_reading"]))
    all_ids = {ng["id"] for ng in nogoods}
    by = {}
    for c in cands: by.setdefault(c["instruction_id"], []).append(c)
    meta = OPT_META(0, False, by)
    meta.update(solver="RC2 weighted MaxSAT (python-sat)", tie_breaking="exact ties are broken by the solver, not by candidate order", candidate_sets_explored=0)

    def hitters(pr): return [i for i, c in enumerate(cands) if any(pr[k] in c["excludes"] and slots[k][1] == c["instruction_id"] for k in range(len(slots)))]
    def unsat(why):
        every = _hits(cands, nogoods, slots)
        rem = sorted(all_ids - every) or sorted(all_ids)
        return {"status": OPT_UNSAT, "tried": 0, "best": None, "remaining_nogoods": rem, "reason": why, **meta}
    if not cands: return unsat("no candidate edit excludes a literal of these nogoods")
    nv = len(cands); X = list(range(1, nv + 1)); top = nv
    w = WCNF()
    for ins, cs in by.items():
        idx = [cands.index(c) for c in cs]
        for a, b in itertools.combinations(idx, 2): w.append([-X[a], -X[b]])
    for ng in nogoods:
        clause = [X[i] for i, c in enumerate(cands) if any(v in c["excludes"] and slots[p][1] == c["instruction_id"] for p, v in ng["_cube"].items())]
        if not clause: return unsat("no candidate edit excludes a literal of these nogoods")
        w.append(clause)
    profiles = sorted(table)
    U4 = len(cands); sumw = sum(c["wording_len"] for c in cands); U3 = (U4 + 1) * sumw; u2 = U4 + U3 + 1; U2 = len(safe) * u2; u1 = U4 + U3 + U2 + 1
    Y, A = {}, {}
    for pr in profiles:
        top += 1; A[pr] = top
        for i in hitters(pr): w.append([-A[pr], -X[i]])
    w.append([A[pr] for pr in profiles])
    for pr in sorted(safe):
        top += 1; Y[pr] = top
        for i in hitters(pr): w.append([-X[i], Y[pr]])
        w.append([-Y[pr]], weight=u2)
    for i, c in enumerate(cands): w.append([-X[i]], weight=u1 + (U4 + 1) * c["wording_len"] + (0 if c["source_aligned"] else 1))
    with RC2(w) as rc2:
        model = rc2.compute()
    if model is None: return unsat("no consistent edit combination hits every nogood without emptying the profile space")
    pos = set(m for m in model if m > 0)
    chosen = [c for i, c in enumerate(cands) if X[i] in pos]
    excl = {c["instruction_id"]: set(c["excludes"]) for c in chosen}
    admitted = {pr for pr in table if not any(pr[k] in excl.get(slots[k][1], ()) for k in range(len(slots)))}
    key = (len(chosen), len(safe - admitted), sum(c["wording_len"] for c in chosen), sum(0 if c["source_aligned"] else 1 for c in chosen))
    all_hit = _hits(chosen, nogoods, slots)
    assert all_hit == all_ids and admitted and not (admitted & bad), "MaxSAT model violates the hard constraints"
    necessity = [{"edit": f"{c['instruction_id']}:{c['keep_reading']}", "nogoods_unsatisfied_without_it": sorted(all_ids - _hits([x for x in chosen if x is not c], nogoods, slots))} for c in chosen]
    return {"status": OPT_OPTIMAL, "tried": 0, "best": (key, chosen, admitted), "remaining_nogoods": [], "necessity_witnesses": necessity, "reason": None, **meta}
