"""Priority 3: the SMT bounded-model-checking path must agree with the engine, and must be able to disagree (negative controls)."""
import unittest, sys, os, copy, io, contextlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import *
from rcpvs.smt_check import crosscheck, check_profile, SUPPORTED
from rcpvs.certificate import _space, _fsms
from rcpvs.checker_rules import derive as ck_derive

NAMES = [n for n in sorted(os.listdir(ROOT)) if os.path.isfile(f"{ROOT}/{n}/expected.json")]


class Agreement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = {}
        for n in NAMES:
            m, s = ex(n); e = json.load(open(f"{ROOT}/{n}/expected.json"))["runs"][0]
            cls.runs[n] = (m,) + pipeline(s, m, e.get("props"), "compile", e.get("limits"))[:1]
    def test_every_fixture_agrees_including_witness_length(self):
        total = 0
        for n, (m, R) in self.runs.items():
            c = crosscheck(R, m); total += c["compared"]
            with self.subTest(n): self.assertEqual(c["disagree"], []); self.assertEqual(c["agree"], c["compared"])
        self.assertGreater(total, 80)
    def test_unsupported_property_types_are_reported_not_hidden(self):
        m, R = self.runs["ack_close"]; c = crosscheck(R, m); self.assertGreater(c["unsupported"], 0); self.assertEqual(c["by_type"]["always_can_complete"], "UNSUPPORTED")
        self.assertNotIn("always_can_complete", SUPPORTED)
    def test_three_party_included(self):
        m, R = self.runs["three_party"]; c = crosscheck(R, m); self.assertGreater(c["compared"], 0); self.assertEqual(c["disagree"], [])
    def test_negative_control_flipped_engine_verdict_is_detected(self):
        m, R = self.runs["scope_ambiguity"]; R = copy.deepcopy(R)
        rec = next(r for r in R["V0"]["table"].values() if r["results"]["P1"]["status"] == VIOLATION); rec["results"]["P1"]["status"] = VERIFIED_SAFE; rec["results"]["P1"]["trace"] = None
        self.assertTrue(crosscheck(R, m)["disagree"])
    def test_negative_control_wrong_witness_length_is_detected(self):
        m, R = self.runs["scope_ambiguity"]; R = copy.deepcopy(R)
        rec = next(r for r in R["V0"]["table"].values() if r["results"]["P1"]["status"] == VIOLATION); rec["results"]["P1"]["trace"] = rec["results"]["P1"]["trace"][:-1] + rec["results"]["P1"]["trace"][-1:] * 2
        self.assertTrue(crosscheck(R, m)["disagree"])
    def test_bound_too_small_is_not_silently_accepted(self):
        m, R = self.runs["scope_ambiguity"]; c = crosscheck(R, m, k=2); self.assertTrue(c["disagree"]); self.assertEqual(c["k"], 2)
    def test_smt_uses_independent_rule_chain(self):
        import rcpvs.smt_check as S, re
        src = open(S.__file__).read(); self.assertFalse(re.search(r"^\s*(from|import)\s+\.?(rcpvs\.)?(spec_analysis|engine|fsm)\b", src, re.M))
    def test_direct_call_semantics(self):
        m, s = ex("scope_ambiguity"); A = ck_derive(s, m); slots, dom, fixed = _space(A, m)
        narrow = _fsms(A, m, slots, fixed, ("narrow",)); broad = _fsms(A, m, slots, fixed, ("broad",))
        p = [x for x in m["properties"] if x["id"] == "P1"][0]
        self.assertEqual(check_profile(narrow, m["system"], p, m.get("messages"), 24)["status"], VIOLATION); self.assertEqual(check_profile(broad, m["system"], p, m.get("messages"), 24)["status"], "NO_VIOLATION_WITHIN_BOUND")
    def test_cli_subcommand(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out): rc = main(["crosscheck", "--spec", f"{ROOT}/multi_violation/spec.txt", "--model", f"{ROOT}/multi_violation/model.json"])
        self.assertEqual(rc, 0); self.assertEqual(json.loads(out.getvalue())["disagree"], [])


if __name__ == "__main__": unittest.main()
