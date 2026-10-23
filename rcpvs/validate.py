"""Input validation (every error names the field). Raises InputError listing ALL problems found."""
from __future__ import annotations
import re

OPERATOR_KEYS = {"ORDER", "MODALITY", "REF", "DEF", "SCOPE", "TOL"}
PROP_TYPES = {"no_orphan_message", "always_can_complete", "can_complete", "inevitable_completion", "deadlock_freedom",
              "unspecified_reception", "forbidden_action", "invalid_transition", "state_invariant", "required_ordering"}
GOAL_TYPES = {"always_can_complete", "can_complete", "inevitable_completion", "deadlock_freedom"}
DEFAULT_ASSUMPTIONS = {"communication": "asynchronous", "channels": "FIFO", "message_loss": False}


class InputError(Exception):
    def __init__(self, errors): self.errors = errors; super().__init__("; ".join(errors))


def normalise_model(model: dict) -> dict:
    """Make communication assumptions explicit (defaults are recorded as defaulted, never silent)."""
    sysm = model.setdefault("system", {})
    a = sysm.setdefault("assumptions", {}); defaulted = []
    for k, v in DEFAULT_ASSUMPTIONS.items():
        if k not in a: a[k] = v; defaulted.append(k)
    if "channel_capacity" not in sysm: sysm["channel_capacity"] = 1; defaulted.append("channel_capacity")
    a["channel_capacity"] = sysm["channel_capacity"]; a["defaulted"] = defaulted
    return model


def validate_model(model: dict, prop_ids=None) -> list:
    E = []
    roles, sysm = model.get("roles"), model.get("system")
    if not isinstance(roles, dict) or not roles: return ["model.roles: missing or empty"]
    if not isinstance(sysm, dict): return ["model.system: missing"]
    msgs_declared = set(model.get("messages", []))
    for rn, r in roles.items():
        st = r.get("states", {})
        if r.get("initial") not in st: E.append(f"model.roles.{rn}.initial: '{r.get('initial')}' is not a declared state")
        ids = set()
        for t in r.get("transitions", []):
            f = f"model.roles.{rn}.transitions[{t.get('id')}]"
            if t.get("id") in ids: E.append(f"{f}: duplicate transition id")
            ids.add(t.get("id"))
            for k in ("src", "dst"):
                if t.get(k) not in st: E.append(f"{f}.{k}: '{t.get(k)}' is not a declared state")
            a = t.get("action", "")
            if not a: E.append(f"{f}.action: empty")
            elif a[0] in "!?" and msgs_declared and a[1:].partition("@")[0] not in msgs_declared: E.append(f"{f}.action: message '{a[1:].partition('@')[0]}' not in model.messages")
    impls = sysm.get("implementations", {})
    if len(impls) < 2: E.append("model.system.implementations: need at least two implementations")
    for n, c in impls.items():
        if c.get("role") not in roles: E.append(f"model.system.implementations.{n}.role: unknown role '{c.get('role')}'")
        if "peer" in c and c["peer"] not in impls: E.append(f"model.system.implementations.{n}.peer: unknown implementation '{c.get('peer')}'")
    cap = sysm.get("channel_capacity")
    if not isinstance(cap, int) or cap < 1: E.append("model.system.channel_capacity: must be a positive integer")
    a = sysm.get("assumptions", {})
    if a.get("communication") != "asynchronous": E.append("model.system.assumptions.communication: only 'asynchronous' is supported")
    if a.get("channels") != "FIFO": E.append("model.system.assumptions.channels: only 'FIFO' is supported")
    if a.get("message_loss") not in (False,): E.append("model.system.assumptions.message_loss: loss is not supported (must be false)")
    # message direction compatibility (n-party): every message an implementation can send must be receivable by its target's role
    recv = {rn: {t["action"][1:].partition("@")[0] for t in r.get("transitions", []) if t.get("action", " ")[0] == "?"} for rn, r in roles.items()}
    for n, c in impls.items():
        if c.get("role") not in roles: continue
        for t in roles[c["role"]].get("transitions", []):
            a_ = t.get("action", " ")
            if a_[0] != "!": continue
            msg, at, who = a_[1:].partition("@"); tgt = who if at else c.get("peer")
            if tgt is None: E.append(f"model.roles.{c['role']}.transitions[{t.get('id')}].action: unaddressed send '{a_}' but implementation '{n}' declares no peer (use '!{msg}@<implementation>')"); continue
            if tgt not in impls: E.append(f"model.roles.{c['role']}.transitions[{t.get('id')}].action: unknown target implementation '{tgt}'"); continue
            if impls[tgt].get("role") in roles and msg not in recv[impls[tgt]["role"]]:
                E.append(f"model.roles.{c['role']}: message '{msg}' sent by '{n}' is never received by peer role '{impls[tgt]['role']}'")
    # definitions
    for term, d in model.get("definitions", {}).items():
        f = f"model.definitions.{term}"
        if not isinstance(d, dict) or not isinstance(d.get("senses"), list) or not d["senses"]: E.append(f"{f}.senses: empty or malformed definition"); continue
        ids = [s_.get("id") for s_ in d["senses"] if isinstance(s_, dict)]
        if len(ids) != len(d["senses"]) or len(set(ids)) != len(ids) or None in ids: E.append(f"{f}.senses: every sense needs a unique id")
        for s_ in d["senses"]:
            if not isinstance(s_, dict) or not isinstance(s_.get("states"), list) or not s_["states"]: E.append(f"{f}.senses[{s_.get('id') if isinstance(s_, dict) else '?'}].states: empty or malformed")
    # bindings
    for iid, b in model.get("bindings", {}).items():
        f = f"model.bindings.{iid}"
        if not isinstance(b, dict): E.append(f"{f}: binding must be an object"); continue
        if b.get("role") not in roles: E.append(f"{f}.role: unknown role '{b.get('role')}'")
        for k in b:
            if k not in OPERATOR_KEYS | {"role", "exclude_texts"}: E.append(f"{f}.{k}: unsupported operator name")
        r_ = roles.get(b.get("role"), {}); tids = {t["id"] for t in r_.get("transitions", [])}; sts = set(r_.get("states", {}))
        def need(field, val, pool, what):
            if val is not None and val not in pool: E.append(f"{f}.{field}: unknown {what} '{val}'")
        def keys(path, d, ks):
            if not isinstance(d, dict): E.append(f"{f}.{path}: must be an object"); return False
            miss = [k for k in ks if k not in d]
            for k in miss: E.append(f"{f}.{path}.{k}: required")
            return not miss
        if "ORDER" in b and keys("ORDER", b["ORDER"], ["first", "second"]): need("ORDER.first", b["ORDER"]["first"], tids, "transition")
        if "MODALITY" in b and keys("MODALITY", b["MODALITY"], []):
            m = b["MODALITY"]
            if not ({"hold", "optional", "prohibit", "relaxed_patch"} & set(m)): E.append(f"{f}.MODALITY: needs at least one of hold / optional / prohibit / relaxed_patch")
            if "hold" in m: need("MODALITY.hold", m["hold"], tids, "transition"); keys("MODALITY", m, ["bypass_action"])
            if "optional" in m and keys("MODALITY.optional", m["optional"], ["id", "src", "dst", "action"]):
                need("MODALITY.optional.src", m["optional"]["src"], sts, "state"); need("MODALITY.optional.dst", m["optional"]["dst"], sts, "state")
            if "prohibit" in m and keys("MODALITY.prohibit", m["prohibit"], ["type"]) and m["prohibit"]["type"] not in PROP_TYPES: E.append(f"{f}.MODALITY.prohibit.type: unknown property type")
        if "REF" in b and keys("REF", b["REF"], ["phrase", "transition", "candidates"]):
            r = b["REF"]; need("REF.transition", r["transition"], tids, "transition")
            cands = r["candidates"]
            if not isinstance(cands, list) or not cands: E.append(f"{f}.REF.candidates: must be a non-empty list")
            else:
                cids = [c.get("id") if isinstance(c, dict) else None for c in cands]
                if None in cids or len(set(cids)) != len(cids): E.append(f"{f}.REF.candidates: every candidate needs a unique id")
                for c in cands:
                    if not isinstance(c, dict) or "msg" not in c: E.append(f"{f}.REF.candidates: candidate missing 'msg'")
                    elif msgs_declared and c["msg"] not in msgs_declared: E.append(f"{f}.REF.candidates[{c.get('id')}].msg: message '{c['msg']}' not in model.messages")
            try: re.compile(r["phrase"])
            except (re.error, TypeError) as e: E.append(f"{f}.REF.phrase: invalid ({e})")
        if "DEF" in b and keys("DEF", b["DEF"], ["term"]):
            d = model.get("definitions", {}).get(b["DEF"]["term"])
            if d is None: E.append(f"{f}.DEF.term: '{b['DEF']['term']}' missing from model.definitions")
            else:
                for s_ in d.get("senses", []):
                    for q in (s_.get("states") or []):
                        if q not in sts: E.append(f"{f}.DEF: definition sense '{s_.get('id')}' references unknown state '{q}' of role '{b.get('role')}'")
        if "SCOPE" in b and keys("SCOPE", b["SCOPE"], ["trigger", "scopes"]):
            sc = b["SCOPE"]["scopes"]
            if not isinstance(sc, list) or not sc: E.append(f"{f}.SCOPE.scopes: must be a non-empty list")
            else:
                for s_ in sc:
                    if not isinstance(s_, dict) or "id" not in s_: E.append(f"{f}.SCOPE.scopes: scope missing 'id'"); continue
                    for t in s_.get("silence", []) + s_.get("disable", []): need(f"SCOPE.scopes[{s_['id']}]", t, tids, "transition")
            try: re.compile(b["SCOPE"]["trigger"])
            except (re.error, TypeError) as e: E.append(f"{f}.SCOPE.trigger: invalid regex ({e})")
        if "TOL" in b and isinstance(b["TOL"], dict):
            tl = b["TOL"]
            if "boundary_transition" not in tl and "tolerance" not in tl: E.append(f"{f}.TOL: needs boundary_transition or tolerance")
            need("TOL.boundary_transition", tl.get("boundary_transition"), tids, "transition")
            if "tolerance" in tl and not (isinstance(tl["tolerance"], dict) and isinstance(tl["tolerance"].get("transition"), dict)): E.append(f"{f}.TOL.tolerance.transition: required object")
        elif "TOL" in b: E.append(f"{f}.TOL: must be an object")
        if isinstance(b.get("MODALITY"), dict) and b["MODALITY"].get("relaxed_cue"):
            try: re.compile(b["MODALITY"]["relaxed_cue"])
            except re.error as e: E.append(f"{f}.MODALITY.relaxed_cue: invalid regex ({e})")
    # properties
    seen = set()
    for p in model.get("properties", []):
        if p.get("id") in seen: E.append(f"model.properties: duplicate id {p.get('id')}")
        seen.add(p.get("id"))
        if p.get("type") not in PROP_TYPES: E.append(f"model.properties.{p.get('id')}.type: unknown property type '{p.get('type')}'")
        if p.get("type") in GOAL_TYPES - {"deadlock_freedom"} and not p.get("goal"): E.append(f"model.properties.{p.get('id')}.goal: required")
        for n in (p.get("goal") or p.get("final") or {}):
            if n not in impls: E.append(f"model.properties.{p.get('id')}.goal: unknown implementation '{n}'")
    for p in model.get("properties", []):
        if p.get("type") == "state_invariant" and not p.get("forbid"): E.append(f"model.properties.{p.get('id')}.forbid: required")
        if p.get("type") == "required_ordering" and not (p.get("later") and p.get("earlier")): E.append(f"model.properties.{p.get('id')}.later/earlier: required")
        if p.get("type") == "forbidden_action" and not (p.get("action") or p.get("tid")): E.append(f"model.properties.{p.get('id')}.action: action or tid required")
    for pid in prop_ids or []:
        if pid not in seen: E.append(f"properties: unknown property id '{pid}'")
    return E


def check_or_raise(model, prop_ids=None):
    normalise_model(model)
    E = validate_model(model, prop_ids)
    if E: raise InputError(E)
    return model


def validate_readings(analysis, model) -> list:
    """Every reading's patch must reference valid transitions/states of the role it modifies."""
    E = []
    for iid, rs in analysis["readings"].items():
        role = model["roles"].get(model["bindings"][iid]["role"]) if iid in model.get("bindings", {}) else None
        if not role: continue
        tids = {t["id"] for t in role["transitions"]}
        for rd in rs:
            for p in rd.patch:
                tid = p.get("remove") or p.get("tid")
                if p["op"] in ("bypass", "remove", "rename_msg", "set_action") and tid not in tids: E.append(f"reading {iid}:{rd.reading_id}: patch references unknown transition '{tid}'")
                if p["op"] == "set_closed":
                    for s in p["states"]:
                        if s not in role["states"]: E.append(f"reading {iid}:{rd.reading_id}: unknown state '{s}'")
                if p["op"] == "add":
                    t = p["t"]
                    for k in ("src", "dst"):
                        if t[k] not in role["states"]: E.append(f"reading {iid}:{rd.reading_id}: added transition {k} '{t[k]}' unknown")
    return E
