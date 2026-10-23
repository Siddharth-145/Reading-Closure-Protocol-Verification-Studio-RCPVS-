"""Task 1: operator tests. Every test drives the real implementation (derive_readings / pipeline), not stored expected JSON."""
import unittest, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import *
from rcpvs.fsm import apply_patches
from rcpvs.tolerance import typed_constraint, evaluate, boundary_table, ACCEPTED, REJECTED, INVALID, UNRESOLVED


def changed_ids(model, role_name, reading):
    base = {t["id"]: t["action"] for t in model["roles"][role_name]["transitions"]}
    new = apply_patches(model["roles"][role_name], [reading]); nt = {t["id"]: t["action"] for t in new["transitions"]}
    return sorted({k for k in set(base) | set(nt) if base.get(k) != nt.get(k)})


class REF(unittest.TestCase):
    def setUp(self): self.m, self.s = ex("ref_ambiguity")
    def test_positive_two_readings_each_changes_only_its_transition(self):
        A = derive_readings(self.s, self.m); rs = A["readings"]["I-01"]
        self.assertEqual([r.reading_id for r in rs], ["request", "ping"])
        self.assertEqual(changed_ids(self.m, "server", rs[0]), ["s3"] if False else [])      # baseline renames to the same message: no change
        self.assertEqual(changed_ids(self.m, "server", rs[1]), ["s3"])                       # alternative changes the intended transition only
    def test_provenance_fields(self):
        r = derive_readings(self.s, self.m)["readings"]["I-01"][1]
        self.assertEqual(r.instruction_id, "I-01"); self.assertEqual(self.s[r.span[0]:r.span[1]], "The server acknowledges it."); self.assertEqual(r.rule_version, "2.0.0")
        self.assertTrue(r.provenance and r.why and r.original_wording and r.affected and r.cue_span is not None)
    def test_negative_missing_phrase_inapplicable(self):
        A = derive_readings("[I-01] The server acknowledges the message.\n", self.m); self.assertEqual(cov(A, "I-01", "REF-1"), COV_INAPPLICABLE); self.assertEqual(A["status"]["I-01"], COV_UNANALYSED)
    def test_single_candidate_not_false_ambiguity(self):
        m = copy.deepcopy(self.m); m["bindings"]["I-01"]["REF"]["candidates"] = m["bindings"]["I-01"]["REF"]["candidates"][:1]
        self.assertEqual(derive_readings(self.s, m)["status"]["I-01"], COV_UNANALYSED)
    def test_explicit_cue_selects_one(self):
        A = derive_readings("[I-01] The server MUST acknowledge the ping.\n", self.m); self.assertEqual([r.reading_id for r in A["readings"]["I-01"]], ["ping"]); self.assertEqual(A["status"]["I-01"], COV_SINGLE)
        A = derive_readings("[I-01] The server acknowledges the request and the ping.\n", self.m); self.assertEqual(A["status"]["I-01"], COV_UNANALYSED)      # two cues: not guessed
    def test_malformed_and_unknown_inputs_rejected(self):
        m = copy.deepcopy(self.m); m["bindings"]["I-01"]["REF"]["transition"] = "zz"; self.assertIn("REF.transition", errs(m))
        m = copy.deepcopy(self.m); m["bindings"]["I-01"]["REF"]["candidates"] = [{"id": "x"}]; self.assertIn("missing 'msg'", errs(m))
        m = copy.deepcopy(self.m); m["bindings"]["I-01"]["REF"]["candidates"] = []; self.assertIn("non-empty", errs(m))
        m = copy.deepcopy(self.m); m["bindings"]["I-01"]["REF"].pop("phrase"); self.assertIn("REF.phrase: required", errs(m))
        m = copy.deepcopy(self.m); m["bindings"]["I-01"]["REF"]["candidates"][0]["msg"] = "NOPE"; self.assertIn("not in model.messages", errs(m))
    def test_phrase_is_escaped(self):
        m = copy.deepcopy(self.m); m["bindings"]["I-01"]["REF"]["phrase"] = "it(s"          # regex metacharacter must not break or broaden the match
        A = derive_readings("[I-01] The server acknowledges it.\n", m); self.assertEqual(cov(A, "I-01", "REF-1"), COV_INAPPLICABLE)
        m["bindings"]["I-01"]["REF"]["phrase"] = "it."; self.assertEqual(cov(derive_readings("[I-01] The server acknowledges its.\n", m), "I-01", "REF-1"), COV_INAPPLICABLE)
    def test_unbound_pronoun_unanalysed(self):
        m = copy.deepcopy(self.m); m["bindings"]["I-01"].pop("REF"); m["bindings"]["I-01"]["ORDER"] = {"first": "s3", "second": "close"}
        self.assertEqual(cov(derive_readings(self.s, m), "I-01", "REF-1"), COV_UNANALYSED)
    def test_end_to_end_and_distinguishing_tests(self):
        R, cert, chk, tests = pipeline(self.s, self.m, None)
        self.assertEqual((R["status_original"], R["final_status"]), (VIOLATION, VERIFIED_SAFE)); self.assertTrue(chk["accepted"]); self.assertEqual(R["edits"][0]["operation"], "disambiguate-reference")
        t = next(x for x in tests if x["kind"] == "alternative_reading_REF")
        self.assertEqual((t["setup"]["baseline_reading"], t["setup"]["alternative_reading"], t["setup"]["depth"]), ("request", "ping", R["limits"]["behaviour_depth"]))
        self.assertIn(("S", "!ACKPING"), [(x["impl"], x["action"]) for x in t["steps"]]); self.assertEqual(t["execution_status"], "replayed_in_model")


class DEF(unittest.TestCase):
    def setUp(self): self.m, self.s = ex("definition_ambiguity")
    def test_two_meanings_two_readings_with_distinct_state_sets(self):
        rs = derive_readings(self.s, self.m)["readings"]["I-01"]; self.assertEqual([r.reading_id for r in rs], ["strict", "half"])
        self.assertEqual([r.patch[0]["states"] for r in rs], [["S3"], ["S2", "S3"]])
        strict = apply_patches(self.m["roles"]["server"], [rs[0]]); half = apply_patches(self.m["roles"]["server"], [rs[1]])
        self.assertEqual([s for s, f in strict["states"].items() if f.get("closed")], ["S3"]); self.assertEqual([s for s, f in half["states"].items() if f.get("closed")], ["S2", "S3"])
    def test_cue_selects_one(self):
        A = derive_readings("[I-01] The server MUST ignore messages once the session is half-closed.\n", self.m); self.assertEqual([r.reading_id for r in A["readings"]["I-01"]], ["half"])
    def test_absent_term_not_triggered_and_undefined_term_not_safe(self):
        A = derive_readings("[I-01] The server MUST ignore messages.\n", self.m); self.assertEqual(cov(A, "I-01", "DEF-1"), COV_INAPPLICABLE); self.assertEqual(A["status"]["I-01"], COV_UNANALYSED)
        m = copy.deepcopy(self.m); m["definitions"] = {}
        self.assertEqual(derive_readings(self.s, m)["status"]["I-01"], COV_UNANALYSED); self.assertIn("missing from model.definitions", errs(m))
        R, *_ = pipeline("[I-01] The server MUST ignore messages.\n", self.m, None); self.assertEqual(R["final_status"], INCOMPLETE)     # never silently safe
    def test_invalid_and_empty_definitions_rejected(self):
        m = copy.deepcopy(self.m); m["definitions"]["closed"]["senses"][0]["states"] = ["NOPE"]; self.assertIn("unknown state 'NOPE'", errs(m))
        m = copy.deepcopy(self.m); m["definitions"]["closed"]["senses"] = []; self.assertIn("empty or malformed definition", errs(m))
        m = copy.deepcopy(self.m); m["definitions"]["closed"]["senses"][0]["states"] = []; self.assertIn("empty or malformed", errs(m))
        with self.assertRaises(InputError): run(self.s, m, None)
    def test_identical_senses_collapse(self):
        m = copy.deepcopy(self.m); m["definitions"]["closed"]["senses"][1]["states"] = ["S3"]; self.assertEqual(derive_readings(self.s, m)["status"]["I-01"], COV_SINGLE)
    def test_end_to_end_clarification_reverified(self):
        R, cert, chk, tests = pipeline(self.s, self.m, None)
        self.assertEqual([(e["instruction_id"], e["keep_reading"], e["operation"]) for e in R["edits"]], [("I-01", "strict", "fix-definition")])
        self.assertEqual(R["final_status"], VERIFIED_SAFE); self.assertEqual(R["targeted_violations_remaining"], []); self.assertTrue(chk["accepted"])
        self.assertTrue(any(t["kind"] == "no_difference_found" for t in tests))       # senses differ in labelling, not in observable actions: no invented test


class SCOPE(unittest.TestCase):
    def setUp(self): self.m, self.s = ex("scope_ambiguity")
    def test_two_distinct_scopes_with_documented_effects(self):
        rs = derive_readings(self.s, self.m)["readings"]["I-01"]; self.assertEqual([r.reading_id for r in rs], ["narrow", "broad"])
        self.assertEqual([[x["id"] for x in r.affected] for r in rs], [["s4"], ["s4", "s6"]])
        self.assertEqual(changed_ids(self.m, "server", rs[0]), ["s4"]); self.assertEqual(changed_ids(self.m, "server", rs[1]), ["s4", "s6"])   # nothing unrelated touched
    def test_cue_only_when_precondition_holds(self):
        self.assertEqual(cov(derive_readings("[I-01] The server MUST NOT reply.\n", self.m), "I-01", "SCOPE-1"), COV_INAPPLICABLE)
        self.assertEqual(derive_readings("[I-01] The server MUST NOT reply to any repeated request in the session.\n", self.m)["status"]["I-01"], COV_SINGLE)
    def test_not_distinct_scopes_declare_no_ambiguity(self):
        m = copy.deepcopy(self.m); m["bindings"]["I-01"]["SCOPE"]["scopes"][1]["silence"] = ["s4"]; self.assertEqual(derive_readings(self.s, m)["status"]["I-01"], COV_SINGLE)
        m = copy.deepcopy(self.m); m["bindings"]["I-01"]["SCOPE"]["scopes"] = m["bindings"]["I-01"]["SCOPE"]["scopes"][:1]; self.assertEqual(derive_readings(self.s, m)["status"]["I-01"], COV_SINGLE)
    def test_invalid_inputs_rejected(self):
        m = copy.deepcopy(self.m); m["bindings"]["I-01"]["SCOPE"]["scopes"][0]["silence"] = ["zz"]; self.assertIn("unknown transition 'zz'", errs(m))
        m = copy.deepcopy(self.m); m["bindings"]["I-01"]["SCOPE"]["scopes"] = []; self.assertIn("non-empty", errs(m))
        m = copy.deepcopy(self.m); m["bindings"]["I-01"]["SCOPE"]["trigger"] = "("; self.assertIn("invalid regex", errs(m))
    def test_narrow_vs_broad_behaviour_and_pipeline(self):
        R, cert, chk, tests = pipeline(self.s, self.m, None); t = R["V0"]["table"]
        self.assertEqual((t[("narrow",)]["status"], t[("broad",)]["status"]), (VIOLATION, VERIFIED_SAFE))
        self.assertEqual([(e["keep_reading"], e["operation"]) for e in R["edits"]], [("broad", "tighten-scope")]); self.assertTrue(chk["accepted"])
        self.assertEqual({tr["id"] for tr in apply_patches(self.m["roles"]["server"], [R["A1"]["readings"]["I-01"][0]])["transitions"]} , {tr["id"] for tr in self.m["roles"]["server"]["transitions"]})   # no transition deleted


class TOL(unittest.TestCase):
    def setUp(self): self.m, self.s = ex("tolerance_boundary")
    def probes(self, c): return {r["case"]: r["verdict"] for r in boundary_table(c)}
    def test_typed_constraint_boundary_table_inclusive(self):
        c = typed_constraint({"comparator": "within", "value": 5, "unit": "seconds"}, True)
        self.assertEqual(self.probes(c), {"zero": ACCEPTED, "just below boundary": ACCEPTED, "exactly at boundary": ACCEPTED, "just above boundary": REJECTED, "negative": INVALID, "missing": INVALID, "wrong unit": REJECTED})
        self.assertEqual(evaluate(c, 4.999)[0], ACCEPTED); self.assertEqual(evaluate(c, 5.001)[0], REJECTED); self.assertEqual(evaluate(c, 5000, "ms")[0], ACCEPTED); self.assertIn("converted", evaluate(c, 5000, "ms")[1])
        self.assertEqual(evaluate(c, 5001, "ms")[0], REJECTED)
    def test_exclusive_differs_only_at_boundary(self):
        inc = self.probes(typed_constraint({"comparator": "within", "value": 5, "unit": "seconds"}, True)); exc = self.probes(typed_constraint({"comparator": "within", "value": 5, "unit": "seconds"}, False))
        self.assertEqual([k for k in inc if inc[k] != exc[k]], ["exactly at boundary"])
    def test_lower_bound_comparator_and_unspecified_tolerance(self):
        c = typed_constraint({"comparator": "at least", "value": 5, "unit": "seconds"}, True); self.assertEqual((evaluate(c, 5)[0], evaluate(c, 4.9)[0], evaluate(c, 9)[0]), (ACCEPTED, REJECTED, ACCEPTED))
        self.assertIsNone(typed_constraint({"comparator": "approximately", "value": 5, "unit": "seconds"}, True)); self.assertEqual(evaluate(None, 5)[0], UNRESOLVED)
        self.assertIsNone(typed_constraint({"comparator": "within", "value": 5, "unit": None}, True))
    def test_reading_carries_typed_numeric_constraint(self):
        rs = derive_readings(self.s, self.m)["readings"]["I-01"]; self.assertEqual([r.reading_id for r in rs], ["inclusive", "exclusive"])
        for r, incl in zip(rs, (True, False)):
            self.assertEqual((r.numeric["value"], r.numeric["unit"], r.numeric["comparator"]), (5, "seconds", "within"))
            self.assertEqual((r.numeric["constraint"]["upper"], r.numeric["constraint"]["upper_inclusive"], r.numeric["constraint"]["lower"]), (5.0, incl, 0.0))
    def test_unanalysed_cases(self):
        for txt in ("approximately 5 seconds", "within 5", "within 5 parsecs"):
            with self.subTest(txt): self.assertEqual(derive_readings(f"[I-01] The client MUST accept a reply received {txt} of the request.\n", self.m)["status"]["I-01"], COV_UNANALYSED)
        self.assertEqual(cov(derive_readings("[I-01] The client MUST accept a reply.\n", self.m), "I-01", "TOL-1"), COV_INAPPLICABLE)
    def test_malformed_binding_rejected(self):
        m = copy.deepcopy(self.m); m["bindings"]["I-01"]["TOL"] = {}; self.assertIn("TOL: needs boundary_transition or tolerance", errs(m))
        m = copy.deepcopy(self.m); m["bindings"]["I-01"]["TOL"]["boundary_transition"] = "zz"; self.assertIn("unknown transition 'zz'", errs(m))
        m = copy.deepcopy(self.m); m["bindings"]["I-01"]["TOL"] = "x"; self.assertIn("TOL: must be an object", errs(m))
    def test_resolution_and_end_to_end_with_boundary_tests(self):
        R, cert, chk, tests = pipeline(self.s, self.m, None)
        self.assertEqual([(e["keep_reading"], e["operation"]) for e in R["edits"]], [("inclusive", "fix-tolerance")]); self.assertTrue(chk["accepted"])
        t = next(x for x in tests if x["kind"] == "boundary_condition"); bv = t["expected"]["boundary_values"]
        self.assertEqual({r["case"]: r["verdict"] for r in bv["baseline_reading"]}["exactly at boundary"], ACCEPTED); self.assertEqual({r["case"]: r["verdict"] for r in bv["alternative_reading"]}["exactly at boundary"], REJECTED)
    def test_scope_statement(self):
        import rcpvs.tolerance as T; self.assertIn("does NOT make the FSM verifier a general", T.__doc__)


class ORDER_and_MODALITY(unittest.TestCase):
    def setUp(self): self.m, self.s = ex("ack_close")
    def test_order(self):
        self.assertEqual([r.reading_id for r in derive_readings(self.s, self.m)["readings"]["I-01"]], ["ordered", "unordered"])
        self.assertEqual(derive_readings("[I-01] The endpoint MUST complete the acknowledgement exchange before closing the session.\n", self.m)["status"]["I-01"], COV_SINGLE)
        m = copy.deepcopy(self.m); m["bindings"]["I-01"]["ORDER"].pop("second"); self.assertIn("ORDER.second: required", errs(m))
    def test_modality_must_not_should_may(self):
        mm, ss = ex("modality_optional"); A = derive_readings(ss, mm)
        self.assertEqual([r.reading_id for r in A["readings"]["I-01"]], ["omitted", "implemented"]); self.assertEqual(A["readings"]["I-02"][0].derived_property["modality"], "MUST NOT")
        self.assertEqual(derive_readings(self.s.replace("SHOULD", "MUST"), self.m)["status"]["I-02"], COV_SINGLE)
        m = copy.deepcopy(self.m); m["bindings"]["I-02"]["MODALITY"] = {}; self.assertIn("needs at least one of hold / optional / prohibit / relaxed_patch", errs(m))
    def test_conditional_and_multi_action_modality(self):
        A = derive_readings("[I-02] If the peer is idle the endpoint SHOULD retain the session and log events.\n", self.m); r = A["readings"]["I-02"][0]
        self.assertTrue(any("conditional" in p for p in r.preconditions)); self.assertTrue(any("multi-action" in p for p in r.preconditions))
    def test_end_to_end(self):
        R, cert, chk, tests = pipeline(self.s, self.m, ["P1", "P3"]); self.assertEqual((R["final_status"], chk["accepted"]), (VERIFIED_SAFE, True))


if __name__ == "__main__": unittest.main()
