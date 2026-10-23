"""Feature 3 (unified FSM model, per-implementation reading assignments) and Feature 4/5 (verification, traces).

Composition semantics (explicit assumptions, recorded in every certificate):
  * asynchronous interleaving: one implementation moves per step;
  * '!M' sends M into the peer's inbound FIFO channel (blocked when channel is full: bound = channel_capacity);
  * '?M' consumes M from the head of own inbound channel; other actions are internal;
  * channels are reliable and ordered; no loss, duplication or reordering.
"""
from __future__ import annotations
import copy
from collections import deque, defaultdict
from .models import VERIFIED_SAFE, VIOLATION, INCOMPLETE


# ---------------------------------------------------------------- reading -> model change
def apply_patches(role: dict, readings: list) -> dict:
    """Apply the model changes of the selected readings to a copy of a role FSM; tag every new transition."""
    r = copy.deepcopy(role)
    for t in r["transitions"]: t.setdefault("tag", "base")
    for rd in readings:
        tag = f"{rd.instruction_id}:{rd.reading_id}"
        for p in rd.patch:
            op = p["op"]
            if op in ("bypass", "remove"):
                tid = p.get("remove") or p["tid"]
                t = next((x for x in r["transitions"] if x["id"] == tid), None)
                if t is None: raise ValueError(f"patch conflict: transition {tid} missing for {tag}")
                r["transitions"].remove(t)
                if op == "bypass":
                    ns = f"{p['action'].upper()}~{tag}"
                    r["states"][ns] = {"closed": p["action"].startswith("close")}
                    r["transitions"].append({"id": f"{tid}'~{tag}", "src": t["src"], "dst": ns, "action": p["action"], "tag": tag})
            elif op == "add":
                r["transitions"].append(dict(p["t"], tag=tag))
            elif op == "rename_msg":
                t = next(x for x in r["transitions"] if x["id"] == p["tid"])
                tg = t["action"][1:].partition("@")[2]; t["action"] = t["action"][0] + p["msg"] + ("@" + tg if tg else ""); t["tag"] = tag
            elif op == "set_action":
                t = next((x for x in r["transitions"] if x["id"] == p["tid"]), None)
                if t is None: raise ValueError(f"patch conflict: transition {p['tid']} missing for {tag}")
                t["action"] = p["action"]; t["tag"] = tag
            elif op == "set_closed":
                for s in r["states"]: r["states"][s]["closed"] = s in p["states"]
    return r


def build_fsms(model: dict, readings_by_impl: dict) -> dict:
    return {n: apply_patches(model["roles"][model["system"]["implementations"][n]["role"]], rs)
            for n, rs in readings_by_impl.items()}


# ---------------------------------------------------------------- composition
def explore(fsms: dict, system: dict, max_states: int = 100000) -> dict:
    names = sorted(fsms); k = {n: i for i, n in enumerate(names)}
    peers = {n: system["implementations"][n].get("peer") for n in names}
    out = {n: defaultdict(list) for n in names}
    for n in names:
        for t in fsms[n]["transitions"]: out[n][t["src"]].append(t)
    cap = system.get("channel_capacity", 1)
    init = (tuple(fsms[n]["initial"] for n in names), tuple(() for _ in names))
    parent, succ, order, q, complete = {init: None}, {}, [init], deque([init]), True
    while q:
        s = q.popleft(); locs, ch = s; edges = []
        for i, n in enumerate(names):
            for t in out[n].get(locs[i], []):
                a, nch = t["action"], ch
                if a[0] == "!":
                    msg, _, tgt = a[1:].partition("@")          # '!M@X' addresses implementation X; '!M' goes to the declared peer
                    j = k[tgt] if tgt else k[peers[n]]
                    if len(ch[j]) >= cap: continue
                    nch = ch[:j] + (ch[j] + (msg,),) + ch[j + 1:]
                elif a[0] == "?":
                    if not ch[i] or ch[i][0] != a[1:].partition("@")[0]: continue
                    nch = ch[:i] + (ch[i][1:],) + ch[i + 1:]
                edges.append((n, t, (locs[:i] + (t["dst"],) + locs[i + 1:], nch)))
        succ[s] = edges
        for n, t, ns in edges:
            if ns not in parent:
                if len(parent) >= max_states: complete = False; continue
                parent[ns] = (s, n, t); order.append(ns); q.append(ns)
    return {"names": names, "init": init, "succ": succ, "parent": parent, "order": order, "complete": complete}


def _path(g, s):
    p = []
    while g["parent"][s] is not None:
        prev, n, t = g["parent"][s]; p.append((n, t, s)); s = prev
    return p[::-1]


def _step(g, i, n, t, s, prev_state):
    names = g["names"]
    return {"step": i, "impl": n, "tid": t["id"], "action": t["action"], "from": prev_state[0][names.index(n)],
            "to": s[0][names.index(n)], "reading": t.get("tag", "base"),
            "locals": dict(zip(names, s[0])), "channels": {x: list(c) for x, c in zip(names, s[1])}}


def _trace(g, edges):
    steps, prev = [], g["init"]
    for i, (n, t, s) in enumerate(edges, 1):
        steps.append(_step(g, i, n, t, s, prev)); prev = s
    return steps


def goal_sets(prop, fsms, key="goal"):
    return {n: ({s for s, f in fsms[n]["states"].items() if f.get("closed")} if "@closed" in v else set(v)) for n, v in prop[key].items()}


def is_orphan(fsms, names, s):
    return any(fsms[n]["states"].get(s[0][i], {}).get("closed") and s[1][i] for i, n in enumerate(names))


def local_receivable(fsm, state):
    """Messages that some local-reachable state of this FSM can still receive (communication ignored)."""
    reach, st = {state}, [state]
    while st:
        x = st.pop()
        for t in fsm["transitions"]:
            if t["src"] == x and t["dst"] not in reach: reach.add(t["dst"]); st.append(t["dst"])
    return {t["action"][1:].partition("@")[0] for t in fsm["transitions"] if t["src"] in reach and t["action"][0] == "?"}


def _final_pred(prop, fsms, names):
    fs = goal_sets(prop, fsms, "final") if prop.get("final") else {n: {x for x, f in fsms[n]["states"].items() if f.get("closed")} for n in names}
    return lambda s: all(s[0][i] in fs[n] for i, n in enumerate(names)) and not any(s[1])


def check_property(prop: dict, fsms: dict, g: dict, system: dict = None, declared=None) -> dict:
    """Structured result. Safe is only returned when exploration completed; violations found in a truncated
    exploration are still sound witnesses (they are real reachable behaviours)."""
    names, t = g["names"], prop["type"]
    base = {"property": prop["id"], "description": prop.get("description", ""), "states_explored": len(g["parent"]), "complete": g["complete"],
            "assumptions": (system or {}).get("assumptions", {}), "reason": None}
    viol = lambda edges, kind: dict(base, status=VIOLATION, trace=_trace(g, edges), witness_kind=kind)
    clean = lambda: dict(base, status=VERIFIED_SAFE if g["complete"] else INCOMPLETE, trace=None,
                         reason=None if g["complete"] else "state limit reached before exploration completed; absence of a witness is not a proof")
    unknown = lambda why: dict(base, status=INCOMPLETE, trace=None, reason=why)
    order, succ = g["order"], g["succ"]
    # ---- state-bad properties
    pred = None
    if t == "no_orphan_message": pred, kind = (lambda s: is_orphan(fsms, names, s)), "message pending for a closed endpoint"
    elif t == "deadlock_freedom":
        fin = _final_pred(prop, fsms, names); pred, kind = (lambda s: not succ.get(s) and not fin(s)), "stuck state: no enabled move and not a final state"
    elif t == "unspecified_reception":
        pred = lambda s: any(s[1][i] and s[1][i][0] not in local_receivable(fsms[n], s[0][i]) for i, n in enumerate(names))
        kind = "message at channel head that the receiver can never consume"
    elif t == "state_invariant":
        def pred(s):
            for f in prop["forbid"]:
                if all(s[0][names.index(n)] in v for n, v in f.get("locals", {}).items()) and (not f.get("channels_empty") or not any(s[1])): return True
            return False
        kind = "forbidden state invariant violated"
    if pred:
        for s in order:
            if pred(s): return viol(_path(g, s), kind)
        return clean()
    # ---- edge-bad properties
    if t in ("forbidden_action", "invalid_transition"):
        msgs = set(declared or [])
        def bad(n, tr):
            if t == "forbidden_action": return ((tr["id"] == prop["tid"]) if prop.get("tid") else tr["action"] == prop["action"]) and prop.get("impl") in (None, n)
            return tr["dst"] not in fsms[n]["states"] or tr["src"] not in fsms[n]["states"] or (bool(msgs) and tr["action"][0] in "!?" and tr["action"][1:].partition("@")[0] not in msgs)
        for s in order:
            for n, tr, ns in succ.get(s, []):
                if bad(n, tr): return viol(_path(g, s) + [(n, tr, ns)], "prohibited / invalid transition taken")
        return clean()
    if t == "required_ordering":
        init = (g["init"], frozenset()); par, q = {init: None}, [init]
        while q:
            s, fl = q.pop(0)
            for n, tr, ns in succ.get(s, []):
                if tr["action"] == prop["later"] and (prop.get("impl") in (None, n)) and n not in fl:
                    edges, cur = [(n, tr, ns)], (s, fl)
                    while par[cur] is not None: cur, e = par[cur]; edges.insert(0, e)
                    return viol(edges, f"'{prop['later']}' performed before '{prop['earlier']}'")
                nf = fl | {n} if tr["action"] == prop["earlier"] else fl
                if (ns, nf) not in par: par[(ns, nf)] = ((s, fl), (n, tr, ns)); q.append((ns, nf))
        return clean()
    # ---- goal-based properties
    if t in ("always_can_complete", "can_complete", "inevitable_completion"):
        gs = goal_sets(prop, fsms)
        goal = lambda s: all(s[0][i] in gs[n] for i, n in enumerate(names)) and not any(s[1])
        if t == "inevitable_completion":
            if goal(g["init"]): return clean()
            par, q, N = {g["init"]: None}, [g["init"]], []
            while q:
                s = q.pop(0); N.append(s)
                for n, tr, ns in succ.get(s, []):
                    if ns in g["parent"] and not goal(ns) and ns not in par: par[ns] = (s, n, tr); q.append(ns)
            back = lambda s: ([] if par[s] is None else back(par[s][0]) + [(par[s][1], par[s][2], s)])
            term = next((s for s in N if not succ.get(s)), None)
            if term is not None: return viol(back(term), "reachable stuck state outside the goal")
            alive, ch = set(N), True
            while ch:
                ch = False
                for s in list(alive):
                    if not any(ns in alive for _, _, ns in succ.get(s, [])): alive.discard(s); ch = True
            if alive:
                r = min(alive, key=lambda x: len(back(x))); e = next((n, tr, ns) for n, tr, ns in succ[r] if ns in alive)
                return viol(back(r) + [e], "reachable cycle that never reaches the goal (livelock: completion not guaranteed)")
            return clean() if g["complete"] else unknown("state limit reached; inevitability not decided")
        pred_map = defaultdict(list)
        for s, es in succ.items():
            for _, _, ns in es: pred_map[ns].append(s)
        good = {s for s in order if goal(s)}; st = list(good)
        while st:
            for p_ in pred_map[st.pop()]:
                if p_ not in good: good.add(p_); st.append(p_)
        doomed = [s for s in order if s not in good]
        if t == "can_complete":                       # reachability only: one completing path is enough
            if g["init"] in good:
                w = next(x for x in order if goal(x)); return dict(base, status=VERIFIED_SAFE, trace=None, supporting_witness=_trace(g, _path(g, w)), witness_kind="one completing path (reachability only, not guaranteed completion)")
            return viol([], "goal not reachable from the initial state") if g["complete"] else unknown("goal not found within the explored states")
        if not doomed: return clean()
        if not g["complete"]: return unknown("state limit reached; cannot conclude a state is doomed")
        edges, cur, seen = _path(g, doomed[0]), doomed[0], {doomed[0]}
        for _ in range(40):
            nxt = next(((n, tr, ns) for n, tr, ns in succ.get(cur, []) if ns not in good and ns not in seen), None)
            if not nxt: break
            edges.append(nxt); cur = nxt[2]; seen.add(cur)
        return viol(edges, "state from which the completion goal is unreachable (deadlock/livelock/bad closure)")
    raise ValueError(f"unknown property type {t}")


def bounded_words(g: dict, depth: int, cap: int = 20000):
    """Representation of 'behaviours' for latitude loss: all event words (impl, action) up to `depth`."""
    words, frontier, trunc = {()}, {(g["init"], ())}, False
    for _ in range(depth):
        nxt = set()
        for st, w in frontier:
            for n, t, ns in g["succ"].get(st, []):
                w2 = w + ((n, t["action"]),); words.add(w2); nxt.add((ns, w2))
        frontier = nxt
        if len(words) > cap: trunc = True; break
    return words, trunc
