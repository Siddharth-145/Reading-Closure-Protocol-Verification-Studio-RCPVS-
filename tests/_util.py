import copy, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
ROOT = os.path.join(os.path.dirname(HERE), "examples")
from rcpvs.models import *
from rcpvs.cli import pipeline, main
from rcpvs.engine import run
from rcpvs.validate import validate_model, normalise_model, InputError
from rcpvs.spec_analysis import derive_readings


def ex(name): return json.load(open(f"{ROOT}/{name}/model.json")), open(f"{ROOT}/{name}/spec.txt").read()
def cov(A, iid, rule): return next(c.status for c in A["coverage"] if c.instruction_id == iid and c.rule_id == rule)
def errs(m, props=None): return "\n".join(validate_model(normalise_model(copy.deepcopy(m)), props))
def role(init, states, trans, closed=()):
    return {"initial": init, "states": {s: ({"closed": True} if s in closed else {}) for s in states}, "transitions": [{"id": i, "src": a, "dst": b, "action": c} for i, a, b, c in trans]}
def prop(i, t, **kw): return dict({"id": i, "kind": "safety", "type": t, "description": i, "scope": "", "assumptions": {}, "bounds": {}}, **kw)
def small(roles, props, cap=2, messages=None):
    m = {"name": "fixture", "roles": roles, "properties": props, "bindings": {}, "definitions": {}, "errata": {}, "default_properties": [p["id"] for p in props],
         "system": {"implementations": {"A": {"role": "a", "peer": "B"}, "B": {"role": "b", "peer": "A"}}, "channel_capacity": cap}}
    if messages: m["messages"] = messages
    return normalise_model(m)
def result(m, pid, **lim):
    R = run("[I-01] The a performs x.\n", m, [pid], "audit", lim or None)         # unbound instruction: coverage INCOMPLETE, property results still computed
    return next(iter(R["V0"]["table"].values()))["results"][pid]
