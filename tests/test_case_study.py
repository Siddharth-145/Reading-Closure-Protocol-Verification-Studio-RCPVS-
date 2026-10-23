"""Priority 1 and 5: the RFC 1122 case study and execution against a real TCP stack. Socket tests skip if loopback sockets are unavailable."""
import unittest, sys, os, json, copy, socket
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import *
CS = os.path.join(os.path.dirname(ROOT), "case_studies", "rfc1122_half_duplex_close"); sys.path.insert(0, CS)
import tcp_harness
from rcpvs.tests_gen import mark_executed
from rcpvs.smt_check import crosscheck

M = json.load(open(f"{CS}/model.json")); SPEC = open(f"{CS}/spec.txt").read()
def loopback():
    try: tcp_harness._pair()[0].close(); return True
    except Exception: return False


class Documents(unittest.TestCase):
    def test_sources_modelling_and_results_exist_and_are_honest(self):
        src, mod, res = (open(f"{CS}/{f}").read() for f in ("SOURCES.md", "MODELLING.md", "RESULTS.md"))
        self.assertIn("RFC 1122", src); self.assertIn("4.2.2.13", src); self.assertIn("https://", src); self.assertIn("No errata link is recorded", src); self.assertIn("**not** retrieved", src)
        self.assertIn("PARAPHRASE", SPEC); self.assertIn("Not claimed", mod); self.assertIn("nothing here says rfc 1122 is defective", res.lower()); self.assertIn("one kernel", res.lower())
    def test_no_rfc_sentence_is_reproduced(self):
        self.assertNotIn("show that data was lost", SPEC)                      # paraphrased, not copied


class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.A = pipeline(SPEC, M, None); veto = copy.deepcopy(M); veto["bindings"]["I-01"]["MODALITY"].pop("omitted_text"); cls.B = pipeline(SPEC, veto, None); cls.veto = veto
    def test_real_sentences_yield_expected_profile_results(self):
        R = self.A[0]; t = {k: v["status"] for k, v in R["V0"]["table"].items()}
        self.assertEqual([k for k, v in t.items() if v == VIOLATION], [("implemented", "relaxed")]); self.assertEqual(R["status_original"], VIOLATION)
        self.assertEqual([n["literals"] for n in R["selected_nogoods"]], [[("R", "I-01", "implemented"), ("R", "I-02", "relaxed")]])
        self.assertEqual(R["coverage_summary0"]["unresolved_instructions"], []); self.assertTrue(all(c.errata == [] for c in R["analysis0"]["instructions"]))
        self.assertTrue(all("(no errata link supplied)" in r.provenance for rs in R["analysis0"]["readings"].values() for r in rs))
    def test_two_scenarios_and_checker(self):
        (RA, _, ka, _), (RB, _, kb, _) = self.A, self.B
        self.assertEqual([(e["instruction_id"], e["keep_reading"]) for e in RA["edits"]], [("I-01", "omitted")]); self.assertEqual([(e["instruction_id"], e["keep_reading"]) for e in RB["edits"]], [("I-02", "enforced")])
        self.assertTrue(ka["accepted"] and kb["accepted"]); self.assertEqual((RA["final_status"], RB["final_status"]), (VERIFIED_SAFE, VERIFIED_SAFE))
        self.assertEqual(RA["property_comparison"]["added"], ["PROH-I-01"])
    def test_smt_agrees_on_case_study(self):
        for R, m in ((self.A[0], M), (self.B[0], self.veto)):
            c = crosscheck(R, m); self.assertEqual(c["disagree"], []); self.assertGreater(c["compared"], 4)


@unittest.skipUnless(loopback(), "loopback sockets unavailable")
class RealStack(unittest.TestCase):
    def steps(self, *pairs): return [{"impl": i, "action": a} for i, a in pairs]
    def test_orderly_close_gives_fin(self):
        r = tcp_harness.run_once(self.steps(("S", "!DATA"), ("R", "?DATA"), ("R", "read"), ("R", "close"), ("S", "?FIN")))
        self.assertTrue(r["reproduced"]); self.assertEqual(r["observations"][-1]["observed"], "FIN")
    def test_close_with_unread_data_gives_rst_not_fin(self):
        r = tcp_harness.run_once(self.steps(("S", "!DATA"), ("R", "?DATA"), ("R", "close"), ("S", "?RST"))); self.assertTrue(r["reproduced"])
        r = tcp_harness.run_once(self.steps(("S", "!DATA"), ("R", "?DATA"), ("R", "close"), ("S", "?FIN")))
        self.assertFalse(r["reproduced"]); self.assertEqual(r["observations"][-1]["observed"], "RST")      # the harness observes, it does not assume
    def test_unmappable_action_is_refused(self):
        with self.assertRaises(ValueError): tcp_harness.run_once(self.steps(("S", "!DATA"), ("R", "explode")))
    def test_execute_records_environment_and_semantics(self):
        R, cert, chk, tests = Pipeline.B; tests = copy.deepcopy(tests); recs = tcp_harness.execute(tests, mark_executed, repeats=3)
        ex_ = [r for r in recs if r["executed"]]; self.assertTrue(ex_)
        for r in ex_:
            self.assertIn("platform", r["environment"]); self.assertIn("pass_semantics", r); self.assertEqual(r["repeats"], 3)
            if r["kind"] == "normal_success_coverage": self.assertEqual(r["reproduced_count"], 3); self.assertTrue(r["passed"])
            else: self.assertEqual(r["reproduced_count"], 0); self.assertTrue(r["passed"])
        done = {t["id"] for t in tests if t["execution_status"] == "executed_against_implementation"}; self.assertEqual(done, {r["test_id"] for r in ex_})
        self.assertTrue(all(t["execution_status"] != "executed_against_implementation" for t in tests if t["id"] not in done))     # only really executed tests are marked
        self.assertTrue(all("environment" in t["external_result"] for t in tests if t["id"] in done))
    def test_flaky_outcomes_get_no_verdict(self):
        seq = iter([True, False, True]); orig = tcp_harness.run_once
        tcp_harness.run_once = lambda steps, timeout=2.0: {"reproduced": next(seq), "observations": []}
        try:
            tests = [{"id": "X1", "kind": "normal_success_coverage", "steps": [{"impl": "S", "action": "!DATA"}], "targets": "t"}]
            recs = tcp_harness.execute(tests, mark_executed, repeats=3); self.assertIsNone(recs[0]["passed"])
        finally: tcp_harness.run_once = orig
    def test_case_study_runner_end_to_end(self):
        import run_case_study; s = run_case_study.main(repeats=2)
        self.assertEqual(set(s["scenarios"]), {"A_tool_default", "B_author_veto_on_I-01"})
        for sc in s["scenarios"].values(): self.assertEqual(sc["checker"], "CERTIFICATE_ACCEPTED"); self.assertEqual(sc["smt"]["disagree"], 0); self.assertTrue(all(e[4] is True for e in sc["executed"]))
        for f in ("report.md", "certificate.json", "conformance_tests.json", "execution_records.json", "smt_crosscheck.json"): self.assertTrue(os.path.isfile(f"{CS}/outputs/B_author_veto_on_I-01/{f}"))


if __name__ == "__main__": unittest.main()
