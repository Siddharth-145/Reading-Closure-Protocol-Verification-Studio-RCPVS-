"""Priority 4: the optional MaxSAT mode must agree with the exact enumeration optimiser on the objective, and fail the same way."""
import unittest, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import *
from rcpvs.maxsat_opt import available
from rcpvs.engine import bad_safe

NAMES = [n for n in sorted(os.listdir(ROOT)) if os.path.isfile(f"{ROOT}/{n}/expected.json")]


@unittest.skipUnless(available(), "python-sat not installed")
class MaxSAT(unittest.TestCase):
    def pair(self, m, s, props, **lim):
        a, *_ = pipeline(s, m, props, "compile", dict(lim, optimiser="enumeration")); b, *_ = pipeline(s, m, props, "compile", dict(lim, optimiser="maxsat")); return a, b
    def test_objective_agrees_with_enumeration_on_every_fixture(self):
        for n in NAMES:
            m, s = ex(n); e = json.load(open(f"{ROOT}/{n}/expected.json"))["runs"][0]
            with self.subTest(n):
                a, b = self.pair(m, s, e.get("props"), **(e.get("limits") or {}))
                self.assertEqual(a["final_status"], b["final_status"])
                if a["rounds"]:
                    self.assertEqual(a["rounds"][0]["objective"], b["rounds"][0]["objective"])          # same lexicographic optimum
                    self.assertEqual(b["optimisation"]["solver"][:3], "RC2")
    def test_interacting_nogoods_and_necessity(self):
        m, s = ex("ack_close")
        for props, k in ((["P1", "P2"], 1), (["P1", "P3"], 2)):
            _, b = self.pair(m, s, props); self.assertEqual(len(b["edits"]), k); self.assertEqual(b["targeted_violations_remaining"], []); self.assertEqual(b["final_status"], VERIFIED_SAFE)
            self.assertTrue(all(x["nogoods_unsatisfied_without_it"] for x in b["rounds"][0]["necessity"])); self.assertTrue(b["optimisation"]["optimality_proved_within_search_space"])
    def test_unsat_matches(self):
        m, s = ex("ref_ambiguity")
        for c in m["bindings"]["I-01"]["REF"]["candidates"]: c.pop("text")
        a, b = self.pair(m, s, None)
        self.assertEqual((a["final_status"], b["final_status"]), (CLAR_UNRESOLVED, CLAR_UNRESOLVED)); self.assertEqual(b["optimisation"]["status"], OPT_UNSAT); self.assertEqual(a["optimisation"]["remaining_nogoods"], b["optimisation"]["remaining_nogoods"])
    def test_latitude_tradeoff_same_as_enumeration(self):
        m, s = ex("ack_close"); a, b = self.pair(m, s, ["P1", "P2"]); self.assertEqual(a["latitude"]["profile_level"]["L"], b["latitude"]["profile_level"]["L"])
    def test_revised_spec_certificate_accepted(self):
        m, s = ex("multi_violation"); R, cert, chk, _ = pipeline(s, m, None, "compile", {"optimiser": "maxsat"}); self.assertTrue(chk["accepted"]); self.assertIn("RC2", cert["limits"]["optimiser"] if False else R["optimisation"]["solver"])
    def test_optimiser_option_validation(self):
        m, s = ex("ack_close")
        with self.assertRaises(InputError): run(s, m, None, "audit", {"optimiser": "magic"})
    def test_report_names_solver(self):
        from rcpvs.report import markdown
        m, s = ex("ack_close"); R, c, k, t = pipeline(s, m, ["P1", "P3"], "compile", {"optimiser": "maxsat"}); self.assertIn("RC2 weighted MaxSAT", markdown(R, m, k, t))
    def test_cli_flag(self):
        import io, contextlib, tempfile
        d = tempfile.mkdtemp()
        with contextlib.redirect_stdout(io.StringIO()): rc = main(["compile", "--spec", f"{ROOT}/ack_close/spec.txt", "--model", f"{ROOT}/ack_close/model.json", "--optimiser", "maxsat", "--out", d])
        self.assertEqual(rc, 0); self.assertIn("RC2", open(f"{d}/report.md").read())


if __name__ == "__main__": unittest.main()
