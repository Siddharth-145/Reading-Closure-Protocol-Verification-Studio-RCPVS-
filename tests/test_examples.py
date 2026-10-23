"""Task 9: one automated integration test per fixture, generated from the examples directory. Fixtures are synthetic."""
import unittest, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import *
sys.path.insert(0, ROOT)
import run_examples

NAMES = sorted(n for n in os.listdir(ROOT) if os.path.isfile(f"{ROOT}/{n}/expected.json"))


class Fixtures(unittest.TestCase):
    def test_all_required_fixtures_present(self):
        need = {"ack_close", "ref_ambiguity", "definition_ambiguity", "scope_ambiguity", "tolerance_boundary", "modality_optional", "mixed_deployment", "common_mode", "multi_violation", "incomplete_coverage"}
        self.assertEqual(need - set(NAMES), set())


def make(name):
    def t(self):
        d = f"{ROOT}/{name}"
        for f in ("spec.txt", "model.json", "expected.json", "README.md"): self.assertTrue(os.path.isfile(f"{d}/{f}"), f)
        e = json.load(open(f"{d}/expected.json")); self.assertTrue(e.get("synthetic")); self.assertIn("Synthetic fixture", open(f"{d}/README.md").read())
        for _, bad in run_examples.run_example(name): self.assertEqual(bad, [])
        m, s = ex(name)                                                      # the pipeline really ran: re-derive and verify rather than trust expected.json
        R, cert, chk, tests = pipeline(s, m, e["runs"][0].get("props"), "compile", e["runs"][0].get("limits"))
        self.assertEqual(R["status_original"], e["runs"][0]["expect"]["original_status"])
        if cert: self.assertTrue(chk["accepted"])
        out = run_examples.run_example(name); self.assertEqual(out, run_examples.run_example(name))      # reproducible
    return t


for n in NAMES: setattr(Fixtures, f"test_fixture_{n}", make(n))


class Claims(unittest.TestCase):
    def test_individual_passes_but_mixed_fails(self):
        m, s = ex("mixed_deployment"); R, *_ = pipeline(s, m, None, "audit"); t = R["V0"]["table"]
        for k in (("ordered", "enforced", "ordered", "enforced"), ("unordered", "enforced", "unordered", "enforced")): self.assertEqual((t[k]["status"], t[k]["class"]), (VERIFIED_SAFE, "common-mode"))
        self.assertEqual((t[("ordered", "enforced", "unordered", "enforced")]["status"], t[("ordered", "enforced", "unordered", "enforced")]["class"]), (VIOLATION, "mixed"))
    def test_revision_resolves_without_removing_permitted_behaviour(self):
        m, s = ex("multi_violation"); R, *_ = pipeline(s, m, None); self.assertEqual((R["final_status"], R["latitude"]["profile_level"]["L"], R["latitude"]["bounded_behaviour"]["L"]), (VERIFIED_SAFE, 0.0, 0.0))


if __name__ == "__main__": unittest.main()
