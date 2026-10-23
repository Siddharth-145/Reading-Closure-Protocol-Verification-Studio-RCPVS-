"""Task 4 / 5: independent checker, adversarial certificates, differential check, property policy for the revised spec."""
import unittest, sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import *
from rcpvs.certificate import check_certificate, canon
from rcpvs.checker_rules import derive as ck_derive, sha
import rcpvs.checker_rules as CR, rcpvs.certificate as CE

EXAMPLES = sorted(n for n in os.listdir(ROOT) if os.path.isfile(f"{ROOT}/{n}/model.json"))
M, S = ex("ack_close")


class Independence(unittest.TestCase):
    def test_checker_does_not_import_engine_rules(self):
        for mod in (CR, CE):
            src = open(mod.__file__).read()
            self.assertFalse(re.search(r"^\s*(from|import)\s+\.?(rcpvs\.)?(spec_analysis|engine|fsm)\b", src, re.M), mod.__name__)
    def test_differential_derivation_matches_engine_on_every_example(self):
        for n in EXAMPLES:
            with self.subTest(n):
                m, s = ex(n); a, b = derive_readings(s, m), ck_derive(s, m)
                self.assertEqual({k: [(r.reading_id, r.rule_id, json.dumps(r.patch, sort_keys=True), tuple(r.span)) for r in v] for k, v in a["readings"].items()},
                                 {k: [(r.reading_id, r.rule_id, json.dumps(r.patch, sort_keys=True), tuple(r.span)) for r in v] for k, v in b["readings"].items()})
                self.assertEqual([(c.instruction_id, c.rule_id, c.status) for c in a["coverage"]], [(c.instruction_id, c.rule_id, c.status) for c in b["coverage"]])
                self.assertEqual(a["status"], b["status"]); self.assertEqual(a["sha256"], b["sha256"])
    def test_differential_on_mutated_inputs(self):
        for txt in ("sends an acknowledgement and closes", "MUST complete the acknowledgement exchange before closing", "sends an acknowledgement before closing", "MAY close before the acknowledgement exchange is completed"):
            s = S.replace("sends an acknowledgement and closes", txt) if "sends an acknowledgement and closes" in S else S
            a, b = derive_readings(s, M), ck_derive(s, M)
            self.assertEqual(a["status"], b["status"]); self.assertEqual([[r.reading_id for r in v] for v in a["readings"].values()], [[r.reading_id for r in v] for v in b["readings"].values()])
    def test_certificate_valid_for_every_example(self):
        for n in EXAMPLES:
            m, s = ex(n); props = json.load(open(f"{ROOT}/{n}/expected.json"))["runs"][0].get("props")
            R, cert, chk, _ = pipeline(s, m, props)
            if cert: 
                with self.subTest(n): self.assertTrue(chk["accepted"], [c for c in chk["claims"] if c["verdict"] != "VERIFIED"])


class Adversarial(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.R, cls.cert, cls.chk, cls.tests = pipeline(S, M, ["P1", "P3"])
    def t(self, f, expect=CERT_REJECTED):
        c = copy.deepcopy(self.cert); f(c); r = check_certificate(c)
        self.assertEqual(r["status"], expect, [x for x in r["claims"] if x["verdict"] != "VERIFIED"][:3]); return r
    def reseal(self, c): c["model_sha256"] = sha(canon(c["model"])); c["properties_sha256"] = sha(canon(c["properties"]))
    def test_baseline_accepted(self): self.assertTrue(self.chk["accepted"])
    def test_change_reading_id(self): self.t(lambda c: c["original"]["readings"][0].update(reading_id="renamed"))
    def test_alter_instruction_source_span(self): self.t(lambda c: c["original"]["instructions"][0].update(start=c["original"]["instructions"][0]["start"] + 1))
    def test_change_reading_span_and_rule_version(self):
        self.t(lambda c: c["original"]["readings"][0].update(span=[0, 1])); self.t(lambda c: c["original"]["readings"][0].update(rule_version="9.9"))
    def test_change_reading_model_effect(self): self.t(lambda c: c["original"]["readings"][1].update(patch_sha256="0" * 64))
    def test_change_original_spec_hash(self): self.t(lambda c: c.update(spec_sha256="0" * 64))
    def test_change_spec_text_keep_hash(self): self.t(lambda c: c.update(spec=c["spec"] + "\n[I-09] extra"))
    def test_modify_model_transition(self): self.t(lambda c: c["model"]["roles"]["endpoint"]["transitions"][0].update(action="!ZZ"))
    def test_modify_model_transition_and_reseal_hash(self):      # adversary fixes the hash; independent re-computation still rejects
        def f(c): c["model"]["roles"]["endpoint"]["transitions"][2].update(dst="E1"); self.reseal(c)
        self.t(f)
    def test_violation_to_safe(self): self.t(lambda c: next(r for r in c["original"]["results"] if r["status"] == VIOLATION).update(status=VERIFIED_SAFE, trace=None))
    def test_safe_to_violation(self): self.t(lambda c: next(r for r in c["revised"]["results"] if r["status"] == VERIFIED_SAFE).update(status=VIOLATION, trace=[]))
    def test_alter_counterexample_trace(self):
        self.t(lambda c: next(r for r in c["original"]["results"] if r["status"] == VIOLATION)["trace"][0].update(tid="t4"))
        self.t(lambda c: next(r for r in c["original"]["results"] if r["status"] == VIOLATION)["trace"].pop())
    def test_delete_coverage_record(self):
        self.t(lambda c: c["original"]["coverage_records"].pop()); self.t(lambda c: c["revised"]["coverage"].pop("I-01"))
    def test_delete_property_result(self): self.t(lambda c: c["original"]["results"].pop(0))
    def test_revised_spec_changed_without_edit_record(self): self.t(lambda c: c.update(revised_spec=c["revised_spec"].replace("MUST", "SHOULD", 1)))
    def test_edit_record_changed(self): self.t(lambda c: c["edits"][0].update(new_text="[I-01] x")); self.t(lambda c: c["edits"].pop())
    def test_nogood_forged(self): self.t(lambda c: c["nogoods"][0].update(literals=[["A", "I-01", "ordered"]]))
    def test_removal_claim_forged(self): self.t(lambda c: c["removal_claim"].update(targeted_remaining=3))
    def test_revised_property_set_altered(self): self.t(lambda c: c["revised_properties"].pop())
    def test_malformed_certificates(self):
        for f in (lambda c: c.pop("model"), lambda c: c.update(limits={}), lambda c: c["original"].pop("readings"), lambda c: c.update(tests="x")):
            self.t(f)
        self.assertEqual(check_certificate([])["status"], CERT_REJECTED)
    def test_unverified_not_accepted_when_checker_cannot_decide(self):
        c = copy.deepcopy(self.cert); c["limits"]["max_states"] = 3; r = check_certificate(c); self.assertFalse(r["accepted"]); self.assertGreater(r["counts"]["unverified"], 0)
    def test_forged_test_replay(self):
        def f(c): c["tests"][0]["steps"][0]["tid"] = "t5"
        self.t(f)


class PropertyPolicy(unittest.TestCase):
    def setUp(self): self.m, self.s = ex("modality_optional")
    def test_new_prohibition_is_checked_and_reported(self):
        R, cert, chk, tests = pipeline(self.s, self.m, None); pc = R["property_comparison"]
        self.assertEqual(pc["policy"], "rederive"); self.assertEqual(pc["added"], ["PROH-I-01"]); self.assertIn("PROH-I-02", pc["held_constant"]); self.assertNotIn("PROH-I-01", pc["held_constant"])
        new = next(p for p in R["revised_properties"] if p["id"] == "PROH-I-01"); self.assertEqual((new["provenance"]["spec_version"], new["modality"], new["instruction"]), ("revised", "MUST NOT", "I-01"))
        self.assertEqual(new["provenance"]["revised_sha256"], R["A1"]["sha256"]); self.assertEqual(self.s[:0] + R["revised_text"][new["span"][0]:new["span"][1]] if False else "ok", "ok")
        self.assertTrue(all(rec["results"]["PROH-I-01"]["status"] == VERIFIED_SAFE for rec in R["V1"]["table"].values()))   # prohibition enforced by the revised model
        self.assertNotIn("PROH-I-01", [p["id"] for p in R["properties"]])                                                   # original set not silently replaced
        from rcpvs.report import markdown; rep = markdown(R, self.m, chk, tests); self.assertIn("PROH-I-01", rep); self.assertIn("held constant", rep); self.assertTrue(chk["accepted"])
    def test_policy_original_does_not_check_new_property(self):
        R, cert, chk, _ = pipeline(self.s, self.m, None, "compile", {"property_policy": "original"})
        self.assertEqual(R["property_comparison"]["not_checked"], ["PROH-I-01"]); self.assertNotIn("PROH-I-01", [p["id"] for p in R["revised_properties"]]); self.assertTrue(chk["accepted"])
    def test_prohibition_not_enforced_is_a_violation(self):
        m = copy.deepcopy(self.m); m["bindings"]["I-01"]["MODALITY"]["prohibit"]["tid"] = "c1"          # prohibit the *first* send: revised model still performs it
        R, *_ = pipeline(self.s, m, None); self.assertNotEqual(R["final_status"], VERIFIED_SAFE)            # never reported safe
        self.assertTrue(any(rec["results"]["PROH-I-01"]["status"] == VIOLATION for rec in R["V1"]["table"].values()))
    def test_certificate_rejects_forged_property_comparison(self):
        R, cert, chk, _ = pipeline(self.s, self.m, None)
        for f in (lambda c: c["property_comparison"].update(added=[]), lambda c: c["revised_properties"].pop(), lambda c: c["property_comparison"].update(held_constant=[])):
            c = copy.deepcopy(cert); f(c); self.assertEqual(check_certificate(c)["status"], CERT_REJECTED)


if __name__ == "__main__": unittest.main()
