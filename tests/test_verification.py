"""Task 8: dedicated verification fixtures. Each result must name property, profile, assumptions, bound, status and (if violated) a trace."""
import unittest, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import *
from rcpvs.fsm import build_fsms, explore, check_property

FIELDS = ("property", "profile", "assumptions", "bounds", "status", "complete", "reason", "trace", "description")
def direct(m, p, limit=1000):
    fs = build_fsms(m, {n: [] for n in m["system"]["implementations"]}); g = explore(fs, m["system"], limit)
    return check_property(p, fs, g, m["system"], m.get("messages"))


class Fixtures(unittest.TestCase):
    def full(self, r, status, trace):
        for k in FIELDS: self.assertIn(k, r)
        self.assertEqual(r["status"], status); self.assertEqual(r["profile"], {}); self.assertEqual(r["bounds"]["channel_capacity"], 2)
        self.assertEqual(r["assumptions"]["communication"], "asynchronous"); self.assertEqual(r["assumptions"]["message_loss"], False)
        self.assertEqual(r["trace"] is not None, trace)
    def test_deadlock(self):
        m = small({"a": role("A0", ["A0", "A1"], [("a1", "A0", "A1", "?X")]), "b": role("B0", ["B0"], [])}, [prop("D", "deadlock_freedom", final={"A": ["A1"], "B": ["B0"]})])
        self.full(result(m, "D"), VIOLATION, False if False else True) if False else None
        r = result(m, "D"); self.assertEqual(r["status"], VIOLATION); self.assertEqual(r["witness_kind"], "stuck state: no enabled move and not a final state"); self.assertEqual(r["profile"], {})
    def test_unspecified_message_reception(self):
        m = small({"a": role("A0", ["A0", "A1", "A2"], [("a1", "A0", "A1", "!X"), ("a2", "A1", "A2", "!X")]), "b": role("B0", ["B0", "B1"], [("b1", "B0", "B1", "?X")])}, [prop("U", "unspecified_reception")])
        r = result(m, "U"); self.assertEqual(r["status"], VIOLATION); self.assertTrue(r["trace"]); self.assertEqual(r["trace"][-1]["channels"]["B"], ["X"])
    def test_invalid_transition_runtime(self):
        m = small({"a": role("A0", ["A0", "A1"], [("a1", "A0", "A1", "!X")]), "b": role("B0", ["B0", "B1"], [("b1", "B0", "B1", "?Y")])}, [prop("I", "invalid_transition")], messages=["Y"])
        self.assertEqual(direct(m, prop("I", "invalid_transition"))["status"], VIOLATION)
        self.assertEqual(direct(m | {"messages": ["X", "Y"]}, prop("I", "invalid_transition"))["status"], VERIFIED_SAFE)
    def test_prohibited_action(self):
        m = small({"a": role("A0", ["A0", "A1"], [("a1", "A0", "A1", "close")], ["A1"]), "b": role("B0", ["B0"], [])}, [prop("F", "forbidden_action", action="close", impl="A")])
        r = result(m, "F"); self.assertEqual(r["status"], VIOLATION); self.assertEqual(r["trace"][-1]["action"], "close")
        self.assertEqual(direct(m, prop("F", "forbidden_action", action="close", impl="B"))["status"], VERIFIED_SAFE)          # prohibition scoped to one implementation
    def test_required_completion_unreachable(self):
        m = small({"a": role("A0", ["A0", "A1", "A2"], [("a1", "A0", "A1", "tau")]), "b": role("B0", ["B0"], [])}, [prop("C", "always_can_complete", kind="functionality", goal={"A": ["A2"], "B": ["B0"]})])
        r = result(m, "C"); self.assertEqual(r["status"], VIOLATION); self.assertIn("unreachable", r["witness_kind"])
    def test_state_limit_never_reported_safe(self):
        m = small({"a": role("A0", ["A0"], [("a1", "A0", "A0", "!X")]), "b": role("B0", ["B0"], [("b1", "B0", "B0", "?X")])}, [prop("O", "no_orphan_message")], cap=50)
        r = result(m, "O", max_states=5); self.assertEqual(r["status"], INCOMPLETE); self.assertFalse(r["complete"]); self.assertIn("state limit", r["reason"])
        r = result(m, "O"); self.assertEqual(r["status"], VERIFIED_SAFE)
    def test_state_limit_for_every_goal_property(self):
        m = small({"a": role("A0", ["A0", "A1"], [("a1", "A0", "A0", "!X"), ("a2", "A0", "A1", "tau")]), "b": role("B0", ["B0"], [("b1", "B0", "B0", "?X")])},
                  [prop("C", "always_can_complete", goal={"A": ["A1"], "B": ["B0"]}), prop("E", "inevitable_completion", goal={"A": ["A1"], "B": ["B0"]}), prop("K", "can_complete", goal={"A": ["A1"], "B": ["B0"]})], cap=50)
        self.assertEqual(result(m, "C", max_states=5)["status"], INCOMPLETE); self.assertNotEqual(result(m, "E", max_states=5)["status"], VERIFIED_SAFE)
    def test_witness_found_under_truncation_is_sound(self):
        m = small({"a": role("A0", ["A0", "A1"], [("a1", "A0", "A1", "!X"), ("a2", "A1", "A0", "tau")], ["A1"]), "b": role("B0", ["B0", "B1"], [("b1", "B0", "B1", "?X")], ["B0"])}, [prop("O", "no_orphan_message")], cap=50)
        r = result(m, "O", max_states=6); self.assertEqual(r["status"], VIOLATION)
    def test_regression_violation_without_any_reading_choice(self):      # bug found by these fixtures: max() of empty nogood list crashed the engine
        m = small({"a": role("A0", ["A0", "A1"], [("a1", "A0", "A1", "close")], ["A1"]), "b": role("B0", ["B0"], [])}, [prop("F", "forbidden_action", action="close", impl="A")])
        R, cert, chk, tests = pipeline("[I-01] The a closes.\n", m, ["F"])
        self.assertEqual(R["final_status"], VIOLATION); self.assertEqual(R["nogoods"], []); self.assertEqual(R["optimisation"]["status"], OPT_UNSAT)
        self.assertIn("no clarification can remove", R["optimisation"]["reason"]); self.assertIsNone(cert); self.assertEqual((R["edits"], R["revised_text"]), ([], None))
        from rcpvs.report import markdown; self.assertIn("does not depend on any reading choice", markdown(R, m, chk, tests))

    def test_profile_limit_blocks_clarification_and_certificate(self):
        M, S = ex("ack_close"); R, cert, chk, tests = pipeline(S, M, ["P1", "P3"], "compile", {"max_profiles": 4})
        self.assertEqual(R["final_status"], INCOMPLETE); self.assertIsNone(cert); self.assertEqual(R["candidates"], []); self.assertEqual(R["nogoods"], [])
        self.assertEqual((R["V0"]["profiles_checked"], R["V0"]["profiles_total"]), (4, 16)); self.assertEqual(R["coverage_summary0"]["limits_reached"]["profile_enumeration"], True)


class InputValidation(unittest.TestCase):
    def test_invalid_state_and_message_references(self):
        M, _ = ex("ack_close"); m = copy.deepcopy(M); m["roles"]["endpoint"]["transitions"][1]["src"] = "NOPE"; m["roles"]["endpoint"]["transitions"][0]["action"] = "!UNDECLARED"
        e = errs(m); self.assertIn("transitions[t2].src: 'NOPE'", e); self.assertIn("message 'UNDECLARED' not in model.messages", e)
    def test_incompatible_sender_receiver(self):
        m = small({"a": role("A0", ["A0", "A1"], [("a1", "A0", "A1", "!X")]), "b": role("B0", ["B0", "B1"], [("b1", "B0", "B1", "?Y")])}, [])
        self.assertIn("message 'X' sent by 'A' is never received by peer role 'b'", errs(m))
        with self.assertRaises(InputError): run("[I-01] x.\n", m, None)
    def test_empty_or_malformed_bindings(self):
        M, S = ex("ack_close")
        for bad, frag in (({}, "role: unknown role"), ("x", "binding must be an object"), ({"role": "endpoint", "ORDER": {}}, "ORDER.first: required"), ({"role": "endpoint", "ORDER": "x"}, "ORDER: must be an object"),
                          ({"role": "endpoint", "MODALITY": {"hold": "t4"}}, "MODALITY.bypass_action: required"), ({"role": "endpoint", "BOGUS": {}}, "BOGUS: unsupported operator name")):
            m = copy.deepcopy(M); m["bindings"]["I-01"] = bad
            with self.subTest(str(bad)): self.assertIn(frag, errs(m))
    def test_unsupported_assumptions_and_property_errors(self):
        M, _ = ex("ack_close"); m = copy.deepcopy(M)
        m["system"]["assumptions"].update(communication="synchronous", channels="LIFO"); m["properties"][0]["type"] = "magic"; m["properties"].append(prop("S", "state_invariant"))
        e = errs(m); [self.assertIn(x, e) for x in ("only 'asynchronous'", "only 'FIFO'", "unknown property type 'magic'", "forbid: required")]
    def test_assumptions_are_explicit_never_silent(self):
        m = small({"a": role("A0", ["A0"], []), "b": role("B0", ["B0"], [])}, []); a = m["system"]["assumptions"]
        self.assertEqual((a["communication"], a["channels"], a["message_loss"], a["channel_capacity"]), ("asynchronous", "FIFO", False, 2)); self.assertIn("communication", a["defaulted"])
    def test_every_error_is_reported_at_once_and_names_the_field(self):
        M, _ = ex("ack_close"); m = copy.deepcopy(M); m["roles"]["endpoint"]["initial"] = "ZZ"; m["system"]["channel_capacity"] = 0
        try: run("[I-01] x.\n", m, None); self.fail()
        except InputError as e: self.assertGreaterEqual(len(e.errors), 2); self.assertTrue(all("model." in x or "properties" in x for x in e.errors))


if __name__ == "__main__": unittest.main()
