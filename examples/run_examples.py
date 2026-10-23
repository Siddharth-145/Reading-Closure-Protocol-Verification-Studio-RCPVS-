"""Runs every example and compares with expected.json. Exit code 1 on any mismatch."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rcpvs.cli import pipeline
D = os.path.dirname(os.path.abspath(__file__))


def run_example(name):
    d = f"{D}/{name}"; model = json.load(open(f"{d}/model.json")); spec = open(f"{d}/spec.txt").read(); exp = json.load(open(f"{d}/expected.json"))
    out = []
    for run in exp["runs"]:
        R, cert, chk, tests = pipeline(spec, model, run.get("props"), "compile", run.get("limits"))
        e, bad = run["expect"], []
        def need(k, got):
            if k in e and e[k] != got: bad.append(f"{k}: expected {e[k]!r}, got {got!r}")
        need("original_status", R["status_original"]); need("final_status", R["final_status"])
        need("edits", [[x["instruction_id"], x["keep_reading"]] for x in R["edits"]])
        if "checker_accepted" in e: need("checker_accepted", bool(chk and chk["accepted"]))
        if "unresolved_instructions" in e: need("unresolved_instructions", R["coverage_summary0"]["unresolved_instructions"])
        t = R["V0"]["table"]
        for k, v in e.get("profile_status", {}).items():
            key = tuple(k.split(",")) if "," in k else None
            hit = [r for pr, r in t.items() if (pr == key if key else key is None and k in pr)]
            if not hit or any(h["status"] != v for h in hit): bad.append(f"profile {k}: expected {v}, got {[h['status'] for h in hit]}")
        for k, v in e.get("profile_class", {}).items():
            hit = [r for pr, r in t.items() if pr == tuple(k.split(","))]
            if not hit or hit[0]["class"] != v: bad.append(f"class {k}: expected {v}")
        out.append((name, bad))
    return out


if __name__ == "__main__":
    rc = 0
    for name in sorted(n for n in os.listdir(D) if os.path.isfile(f"{D}/{n}/expected.json")):
        for _, bad in run_example(name):
            print(("PASS " if not bad else "FAIL ") + name, *bad, sep="\n   " if bad else " "); rc |= bool(bad)
    sys.exit(rc)
