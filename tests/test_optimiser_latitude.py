"""Tasks 6 and 7: optimiser (objective, search accounting, unsat, limits) and honest latitude-loss measurement."""
import unittest, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import *
from rcpvs.engine import loss, bad_safe

M, S = ex("ack_close")


class Optimiser(unittest.TestCase):
    def test_objective_and_search_accounting_reported(self):
        R, *_ = pipeline(S, M, ["P1", "P3"]); o = R["optimisation"]
        self.assertEqual(o["status"], OPT_OPTIMAL); self.assertTrue(o["optimality_proved_within_search_space"]); self.assertGreater(o["candidate_sets_explored"], 0)
        self.assertEqual(o["candidate_sets_explored"], o["search_space_size"]); self.assertIn("minimise number of edits", " ".join(o["objective"])); self.assertIn("first-found", o["tie_breaking"])
    def test_two_interacting_nogoods_all_violations_eliminated(self):
        R, *_ = pipeline(S, M, ["P1", "P2"]); self.assertTrue(any(len(n["literals"]) == 2 for n in R["nogoods"])); self.assertGreaterEqual(len(R["nogoods"]), 2)
        self.assertEqual(R["targeted_violations_remaining"], []); bad, _, _ = bad_safe(R["V1"]); self.assertEqual(bad, set())            # nothing in scope still violates
        adm = set(R["admitted_original_profiles"]); orig_bad, _, _ = bad_safe(R["V0"]); self.assertFalse(adm & orig_bad)
        self.assertEqual(R["final_status"], VERIFIED_SAFE)
    def test_lexicographic_choice(self):
        R, *_ = pipeline(S, M, ["P1", "P2"]); self.assertEqual(len(R["edits"]), 1)                    # fewest edits beats source-aligned wording
        R, *_ = pipeline(S, M, ["P1", "P3"]); self.assertEqual(len(R["edits"]), 2)                    # both needed: each necessity witness non-empty
        self.assertTrue(all(n["nogoods_unsatisfied_without_it"] for n in R["rounds"][0]["necessity"]))
    def test_search_incomplete_is_never_success(self):
        R, *_ = pipeline(S, M, ["P1", "P3"], "compile", {"max_combos": 1})
        self.assertEqual(R["optimisation"]["status"], OPT_LIMIT); self.assertFalse(R["optimisation"]["optimality_proved_within_search_space"])
        self.assertEqual(R["final_status"], CLAR_UNRESOLVED); self.assertIn("search limit", R["unresolved_reason"]); self.assertEqual(R["edits"], []); self.assertEqual(R["revised_text"], S)
    def test_limit_with_best_found_is_not_proved_optimal(self):
        for k in range(2, 10):
            R, *_ = pipeline(S, M, ["P1", "P3"], "compile", {"max_combos": k})
            if R["edits"]: self.assertEqual(R["optimisation"]["status"], OPT_LIMIT); self.assertFalse(R["optimisation"]["optimality_proved_within_search_space"]); return
        self.skipTest("optimum found only after the full space")
    def test_no_valid_clarification(self):
        m, s = ex("ref_ambiguity")
        for c in m["bindings"]["I-01"]["REF"]["candidates"]: c.pop("text")
        R, *_ = pipeline(s, m, None); o = R["optimisation"]
        self.assertEqual((R["final_status"], o["status"], o["remaining_nogoods"], R["edits"], R["revised_text"]), (CLAR_UNRESOLVED, OPT_UNSAT, ["NG-01"], [], s)); self.assertTrue(o["optimality_proved_within_search_space"])
    def test_edit_types_and_exclude_reading(self):
        R, *_ = pipeline(S, M, ["P1", "P3"], "audit"); self.assertEqual({c["operation"] for c in R["candidates"]}, {"clarify-event-order", "change-constraint-strength"})
        m = copy.deepcopy(M); R, *_ = pipeline(S, m, ["P1"], "audit"); self.assertTrue(R["candidates"])


class Latitude(unittest.TestCase):
    def test_loss_function(self):
        self.assertEqual(loss({1, 2, 3, 4}, {1, 2, 3, 4})["L"], 0.0); self.assertEqual(loss({1, 2, 3, 4}, {1, 2, 3})["L"], 0.25); self.assertEqual(loss({1, 2}, {5})["L"], 1.0)
    def test_empty_baseline_is_explicit_not_zero(self):
        r = loss(set(), {1}); self.assertIsNone(r["L"]); self.assertEqual(r["status"], "UNDEFINED_EMPTY_BASELINE")
    def test_three_cases(self):
        R1, *_ = pipeline(S, M, ["P1", "P3"]); R2, *_ = pipeline(S, M, ["P1", "P2"]); R3, *_ = pipeline(S, M, ["P1", "P2"], "compile", {"max_words": 20})
        for R in (R1, R2): self.assertEqual(R["latitude"]["comparison_status"], "COMPLETE_WITHIN_DEPTH")
        self.assertEqual((R1["latitude"]["profile_level"]["L"], R1["latitude"]["bounded_behaviour"]["L"]), (0.0, 0.0))             # nothing permitted lost
        self.assertGreater(R2["latitude"]["profile_level"]["L"], 0); self.assertGreater(R2["latitude"]["bounded_behaviour"]["L"], 0)    # permitted behaviour lost
        self.assertEqual(R3["latitude"]["comparison_status"], "INCOMPLETE_TRUNCATED"); self.assertTrue(R3["latitude"]["bounded_behaviour"]["truncated"])
    def test_definitions_depth_and_separate_measures_recorded(self):
        R, *_ = pipeline(S, M, ["P1", "P2"], "compile", {"behaviour_depth": 6}); L = R["latitude"]
        self.assertEqual(L["bounded_behaviour"]["depth"], 6); self.assertIn("event word", L["behaviour_definition"]); self.assertIn("identical before and after", L["observation_rules"])
        self.assertNotEqual(L["profile_level"]["L"], L["bounded_behaviour"]["L"])                                                    # separate measures
    def test_report_never_claims_complete_comparison(self):
        from rcpvs.report import markdown
        R, c, k, t = pipeline(S, M, ["P1", "P2"], "compile", {"max_words": 20}); rep = markdown(R, M, k, t)
        self.assertIn("INCOMPLETE_TRUNCATED", rep); self.assertIn("NOT a comparison of every possible execution", rep)


if __name__ == "__main__": unittest.main()
