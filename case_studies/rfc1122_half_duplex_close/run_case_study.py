"""Runs the RFC 1122 4.2.2.13 case study end to end: audit, compile, SMT cross-check, execution against the real TCP stack.
Outputs go to outputs/. Re-run:  python case_studies/rfc1122_half_duplex_close/run_case_study.py"""
import copy, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(os.path.dirname(HERE))); sys.path.insert(0, HERE)
from rcpvs.cli import pipeline
from rcpvs.report import markdown
from rcpvs.smt_check import crosscheck
from rcpvs.tests_gen import mark_executed
import tcp_harness


def scenarios():
    m = json.load(open(f"{HERE}/model.json")); spec = open(f"{HERE}/spec.txt").read()
    veto = copy.deepcopy(m); veto["bindings"]["I-01"]["MODALITY"].pop("omitted_text")          # author vetoes any edit that removes the MAY option
    return spec, {"A_tool_default": m, "B_author_veto_on_I-01": veto}


def main(repeats=5):
    spec, models = scenarios(); out = f"{HERE}/outputs"; os.makedirs(out, exist_ok=True); summary = {"environment": tcp_harness.environment(), "scenarios": {}}
    for name, m in models.items():
        d = f"{out}/{name}"; os.makedirs(d, exist_ok=True)
        if name.startswith("A"):                                  # audit mode first, as recommended for real specifications
            Ra, *_ = pipeline(spec, m, None, "audit"); open(f"{d}/audit_report.md", "w").write(markdown(Ra, m))
        R, cert, chk, tests = pipeline(spec, m, None, "compile")
        records = tcp_harness.execute(tests, mark_executed, repeats)
        cc = crosscheck(R, m)
        open(f"{d}/report.md", "w").write(markdown(R, m, chk, tests)); open(f"{d}/revised_spec.txt", "w").write(R["revised_text"])
        json.dump(cert, open(f"{d}/certificate.json", "w"), indent=1); json.dump(tests, open(f"{d}/conformance_tests.json", "w"), indent=1)
        json.dump(records, open(f"{d}/execution_records.json", "w"), indent=1); json.dump(cc, open(f"{d}/smt_crosscheck.json", "w"), indent=1, default=str)
        summary["scenarios"][name] = {"original_status": R["status_original"], "final_status": R["final_status"], "checker": chk["status"],
            "edits": [(e["instruction_id"], e["keep_reading"], e["new_text"]) for e in R["edits"]], "latitude_profile_level": R["latitude"]["profile_level"]["L"],
            "smt": {k: cc[k] for k in ("k", "compared", "agree")} | {"disagree": len(cc["disagree"]), "unsupported": cc["unsupported"]},
            "executed": [(r["test_id"], r["kind"], r["targets"], f"{r['reproduced_count']}/{r['repeats']}", r["passed"]) for r in records if r["executed"]]}
    json.dump(summary, open(f"{out}/summary.json", "w"), indent=1); return summary


if __name__ == "__main__": print(json.dumps(main(), indent=1))
