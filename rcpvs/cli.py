"""CLI: audit / compile / check / dot. Errors name the offending input or field (exit code 2)."""
import argparse, json, os, sys
from .engine import run
from .certificate import build_certificate, check_certificate
from .tests_gen import generate_tests
from .report import markdown, dot
from .validate import InputError


def pipeline(spec_text, model, props=None, mode="compile", limits=None, with_tests=True):
    R = run(spec_text, model, props, mode, limits)
    tests, cert, chk = [], None, None
    if mode == "compile" and R["revised_text"] is not None and not R["V0"]["truncated"]:
        V1, A1 = R["V1"], R["A1"]
        tests = generate_tests(A1, model, V1, R["limits"], R) if with_tests else []
        for t in tests: t["certified"] = (t["kind"] in {"normal_success_coverage", "counterexample", "boundary_condition", "distinguishing_safe_alternatives"} or t["kind"].startswith("alternative_reading_")) and bool(t["steps"]) and all("tid" in s for s in t["steps"])
        cert = build_certificate(R, model, [t for t in tests if t["certified"]])
        chk = check_certificate(cert)
        ok_ids = {c["claim"].split()[2] for c in chk["claims"] if c["claim"].startswith("conformance test") and c["verdict"] == "VERIFIED"}
        for t in tests:
            t["certified"] = t["certified"] and chk["accepted"] and t["id"] in ok_ids
            if t["certified"]: t["execution_status"] = "replayed_in_model"
    return R, cert, chk, tests


def _load(path, what, kind):
    if not os.path.isfile(path): raise InputError([f"{what}: file not found: {path}"])
    txt = open(path, encoding="utf-8").read()
    if kind == "json":
        try: return json.loads(txt)
        except json.JSONDecodeError as e: raise InputError([f"{what} ({path}): malformed JSON at line {e.lineno} column {e.colno}: {e.msg}"])
    return txt


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rcpvs")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("audit", "compile"):
        p = sub.add_parser(name); p.add_argument("--spec", required=True); p.add_argument("--model", required=True)
        p.add_argument("--props"); p.add_argument("--out", default="out"); p.add_argument("--max-states", type=int); p.add_argument("--max-profiles", type=int); p.add_argument("--optimiser", choices=["enumeration", "maxsat"])
    x = sub.add_parser("crosscheck"); x.add_argument("--spec", required=True); x.add_argument("--model", required=True); x.add_argument("--props"); x.add_argument("--k", type=int, default=24)
    c = sub.add_parser("check"); c.add_argument("certificate")
    d = sub.add_parser("dot"); d.add_argument("--model", required=True); d.add_argument("--role", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "check":
            r = check_certificate(_load(a.certificate, "certificate", "json")); print(json.dumps(r, indent=1)); return 0 if r["accepted"] else 2
        model = _load(a.model, "model", "json")
        if a.cmd == "dot":
            if a.role not in model.get("roles", {}): raise InputError([f"--role: unknown role '{a.role}'"])
            print(dot(model, a.role)); return 0
        spec = _load(a.spec, "specification", "text")
        if a.cmd == "crosscheck":
            from .smt_check import crosscheck
            R = run(spec, model, a.props.split(",") if a.props else None, "compile"); r = crosscheck(R, model, a.k)
            print(json.dumps(r, indent=1, default=str)); return 0 if not r["disagree"] else 2
        props = a.props.split(",") if a.props else None
        lim = {k: v for k, v in (("max_states", a.max_states), ("max_profiles", a.max_profiles), ("optimiser", a.optimiser)) if v}
        R, cert, chk, tests = pipeline(spec, model, props, a.cmd, lim or None)
    except InputError as e:
        for m in e.errors: print("error:", m, file=sys.stderr)
        return 2
    os.makedirs(a.out, exist_ok=True)
    open(f"{a.out}/report.md", "w").write(markdown(R, model, chk, tests))
    if R["revised_text"] is not None: open(f"{a.out}/revised_spec.txt", "w").write(R["revised_text"])
    if cert: json.dump(cert, open(f"{a.out}/certificate.json", "w"), indent=1)
    if tests: json.dump(tests, open(f"{a.out}/conformance_tests.json", "w"), indent=1)
    print(f"original: {R['status_original']}  final: {R['final_status']}  checker: {chk['status'] if chk else 'n/a'}  -> {a.out}/")
    return 0


if __name__ == "__main__": sys.exit(main())
