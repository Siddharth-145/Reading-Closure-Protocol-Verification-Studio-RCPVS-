"""Priority 2: more than two participants (addressed sends, per-implementation mailboxes)."""
import unittest, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import *
from rcpvs.certificate import check_certificate
from rcpvs.fsm import build_fsms, explore

M, S = ex("three_party")


class NParty(unittest.TestCase):
    def test_three_implementations_slots_and_classes(self):
        R, *_ = pipeline(S, M, None, "audit"); V = R["V0"]
        self.assertEqual(V["slots"], [("P1", "I-01"), ("P2", "I-01")]); self.assertEqual(len(V["table"]), 4)
        cls = {k: v["class"] for k, v in V["table"].items()}
        self.assertEqual(cls[("ordered", "ordered")], "common-mode"); self.assertEqual(cls[("unordered", "unordered")], "common-mode"); self.assertEqual(cls[("ordered", "unordered")], "mixed")
        st = {k: v["status"] for k, v in V["table"].items()}
        self.assertEqual(st[("ordered", "ordered")], VERIFIED_SAFE); self.assertEqual(st[("unordered", "unordered")], VIOLATION)
    def test_addressing_delivers_only_to_target(self):
        R, *_ = pipeline(S, M, None, "audit"); tr = R["V0"]["table"][("ordered", "ordered")]["results"]["P2"]
        fs = build_fsms(M, {n: [] for n in M["system"]["implementations"]}); g = explore(fs, M["system"], 1000)
        names = g["names"]; self.assertEqual(names, ["C", "P1", "P2"])
        after_first = next(ns for n, t, ns in g["succ"][g["init"]] if t["action"] == "!DATA@P1")
        self.assertEqual({n: list(c) for n, c in zip(names, after_first[1])}, {"C": [], "P1": ["DATA"], "P2": []})      # P2's mailbox untouched
    def test_trace_names_addressed_actions_and_all_three_channels(self):
        R, *_ = pipeline(S, M, None, "audit"); w = next(x for x in R["witnesses"] if x["property_id"] == "P2")
        self.assertTrue(any(s["action"].startswith("!DATA@") for s in w["trace"])); self.assertEqual(set(w["trace"][0]["channels"]), {"C", "P1", "P2"})
    def test_pipeline_and_independent_checker_on_three_parties(self):
        R, cert, chk, tests = pipeline(S, M, None)
        self.assertEqual((R["status_original"], R["final_status"]), (VIOLATION, VERIFIED_SAFE)); self.assertTrue(chk["accepted"], [c for c in chk["claims"] if c["verdict"] != "VERIFIED"])
        self.assertEqual([(e["instruction_id"], e["keep_reading"]) for e in R["edits"]], [("I-01", "ordered")])
        self.assertTrue(any(t["certified"] for t in tests))
    def test_validation_of_addressing(self):
        m = copy.deepcopy(M); m["roles"]["participant"]["transitions"][1]["action"] = "!ACK"                       # unaddressed send, no peer declared
        self.assertIn("unaddressed send '!ACK'", errs(m))
        m = copy.deepcopy(M); m["roles"]["participant"]["transitions"][1]["action"] = "!ACK@ZZ"; self.assertIn("unknown target implementation 'ZZ'", errs(m))
        m = copy.deepcopy(M); m["roles"]["participant"]["transitions"][1]["action"] = "!ACK@P2"; self.assertIn("never received by peer role 'participant'", errs(m))
        m = copy.deepcopy(M); m["system"]["implementations"]["P1"]["peer"] = "Q"; self.assertIn("implementations.P1.peer", errs(m))
    def test_tampered_three_party_certificate_rejected(self):
        R, cert, chk, _ = pipeline(S, M, None); c = copy.deepcopy(cert)
        next(r for r in c["original"]["results"] if r["status"] == VIOLATION)["trace"][0]["tid"] = "c3"; self.assertEqual(check_certificate(c)["status"], CERT_REJECTED)
    def test_two_party_peer_semantics_unchanged(self):
        m, s = ex("ack_close"); R, *_ = pipeline(s, m, ["P1", "P3"]); self.assertEqual(R["final_status"], VERIFIED_SAFE)


if __name__ == "__main__": unittest.main()
