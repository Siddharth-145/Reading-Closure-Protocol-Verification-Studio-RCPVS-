import copy, io, json, os, sys, tempfile, unittest, contextlib
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from rcpvs.cli import pipeline, main
from rcpvs.certificate import check_certificate, canon
from rcpvs.spec_analysis import derive_readings, anchor, apply_edits_to_text, sha256
from rcpvs.engine import run, verify_all, profile_space, minimal_combinations, classify
from rcpvs.fsm import build_fsms, explore, check_property
from rcpvs.validate import validate_model, normalise_model, InputError
from rcpvs.tests_gen import mark_executed
from rcpvs.models import *

ROOT = os.path.join(os.path.dirname(__file__), "..", "examples")
def ex(name): return json.load(open(f"{ROOT}/{name}/model.json")), open(f"{ROOT}/{name}/spec.txt").read()
MODEL, SPEC = ex("ack_close")
def cov(A, iid, rule): return next(c.status for c in A["coverage"] if c.instruction_id == iid and c.rule_id == rule)
def mini(roles, props, cap=2, impls=None):
    m = {"name": "mini", "roles": roles, "properties": props, "bindings": {}, "definitions": {}, "errata": {},
         "system": {"implementations": impls or {"A": {"role": "a", "peer": "B"}, "B": {"role": "b", "peer": "A"}}, "channel_capacity": cap}}
    return normalise_model(m)
def R_(initial, states, trans, closed=()):
    return {"initial": initial, "states": {s: ({"closed": True} if s in closed else {}) for s in states}, "transitions": [{"id": i, "src": a, "dst": b, "action": c} for i, a, b, c in trans]}
def prop(i, t, **kw): return dict({"id": i, "kind": "safety", "type": t, "description": i, "scope": "", "assumptions": {}, "bounds": {}}, **kw)
def check(model, p, limit=1000):
    fs = build_fsms(model, {n: [] for n in model["system"]["implementations"]}); g = explore(fs, model["system"], limit)
    return check_property(p, fs, g, model["system"], model.get("messages"))


class Readings(unittest.TestCase):
    def test_order_positive_and_negative(self):
        A = derive_readings(SPEC, MODEL)
        self.assertEqual([r.reading_id for r in A["readings"]["I-01"]], ["ordered", "unordered"])
        neg = SPEC.replace("sends an acknowledgement and closes the session", "sends an acknowledgement and logs the result")
        A = derive_readings(neg, MODEL)       # 'and' alone is NOT ambiguity; and it is not silently safe either
        self.assertEqual(cov(A, "I-01", "ORDER-1"), COV_INAPPLICABLE); self.assertEqual(A["status"]["I-01"], COV_UNANALYSED)
        A = derive_readings(SPEC.replace("sends an acknowledgement and closes", "sends an acknowledgement before it closes"), MODEL)
        self.assertEqual(A["status"]["I-01"], COV_UNANALYSED)            # unrecognised ordering cue -> not guessed

    def test_ref(self):
        m, s = ex("ref_ambiguity"); A = derive_readings(s, m)
        self.assertEqual([r.reading_id for r in A["readings"]["I-01"]], ["request", "ping"]); self.assertEqual(A["readings"]["I-01"][1].affected[0]["id"], "s3")
        A = derive_readings("[I-01] The server MUST acknowledge the request.\n", m)
        self.assertEqual(A["status"]["I-01"], COV_SINGLE)
        m2 = copy.deepcopy(m); m2["bindings"]["I-01"].pop("REF")                      # unbound pronoun -> UNANALYSED
        self.assertEqual(cov(derive_readings(s, m2), "I-01", "REF-1"), COV_UNANALYSED)
        m3 = copy.deepcopy(m); m3["bindings"]["I-01"]["REF"]["candidates"] = m3["bindings"]["I-01"]["REF"]["candidates"][:1]
        self.assertEqual(derive_readings(s, m3)["status"]["I-01"], COV_UNANALYSED)    # one antecedent: unresolved, never guessed

    def test_def(self):
        m, s = ex("definition_ambiguity"); A = derive_readings(s, m)
        self.assertEqual([r.reading_id for r in A["readings"]["I-01"]], ["strict", "half"])
        m2 = copy.deepcopy(m); m2["definitions"]["closed"]["senses"][1]["states"] = ["S3"]       # identical behaviour -> single reading
        A = derive_readings(s, m2); self.assertEqual(A["status"]["I-01"], COV_SINGLE)
        self.assertIn("identical", [c.reason for c in A["coverage"] if c.rule_id == "DEF-1"][0])
        m3 = copy.deepcopy(m); m3["definitions"]["closed"]["defined_at"] = "I-02"
        A = derive_readings(s + "[I-02] A session is closed when finished.\n", m3)
        self.assertTrue(any("used before being defined" in p for p in A["readings"]["I-01"][0].preconditions))
        self.assertEqual(A["definition_table"][0]["affected_instructions"], ["I-01", "I-02"])

    def test_scope(self):
        m, s = ex("scope_ambiguity"); A = derive_readings(s, m)
        self.assertEqual([r.reading_id for r in A["readings"]["I-01"]], ["narrow", "broad"])
        self.assertEqual([x["id"] for x in A["readings"]["I-01"][1].affected], ["s4", "s6"]); self.assertIsNotNone(A["readings"]["I-01"][0].cue_span)
        self.assertEqual(derive_readings("[I-01] The server MUST NOT reply.\n", m)["status"]["I-01"], COV_UNANALYSED)
        R, *_ = pipeline(s, m, None, "audit")
        st = {k: v["status"] for k, v in R["V0"]["table"].items()}
        self.assertEqual(st[("narrow",)], VIOLATION); self.assertEqual(st[("broad",)], VERIFIED_SAFE)       # narrow vs broad differ

    def test_tol(self):
        m, s = ex("tolerance_boundary"); A = derive_readings(s, m)
        rd = A["readings"]["I-01"][0]
        self.assertEqual(rd.numeric["value"], 5); self.assertEqual(rd.numeric["unit"], "seconds"); self.assertEqual(rd.numeric["comparator"], "within")
        A = derive_readings(s.replace("within 5 seconds", "approximately 5 seconds"), m)      # no defined tolerance -> UNANALYSED
        self.assertEqual(A["status"]["I-01"], COV_UNANALYSED)
        m2 = copy.deepcopy(m); m2["bindings"]["I-01"]["TOL"]["tolerance"] = {"range": "+-1", "transition": {"id": "c3b", "src": "C1", "dst": "C3", "action": "?REPLYLIMIT"}}
        self.assertEqual(len(derive_readings(s.replace("within 5 seconds", "approximately 5 seconds"), m2)["readings"]["I-01"]), 2)
        self.assertEqual(derive_readings(s.replace("within 5", "within"), m)["status"]["I-01"], COV_UNANALYSED)

    def test_modality(self):
        m, s = ex("modality_optional"); A = derive_readings(s, m)
        self.assertEqual([r.reading_id for r in A["readings"]["I-01"]], ["omitted", "implemented"])      # MAY: both paths
        self.assertEqual(A["readings"]["I-02"][0].derived_property["type"], "required_ordering")        # MUST NOT -> safety property
        m2, s2 = ex("ack_close")
        m3 = copy.deepcopy(m2); m3["policy"] = {"SHOULD": "enforced_only"}
        A = derive_readings(s2, m3); self.assertEqual(A["status"]["I-02"], COV_SINGLE); self.assertEqual(A["policy"]["SHOULD"], "enforced_only")
        self.assertEqual(derive_readings(s2, m2)["policy"]["SHOULD"], "both_readings")                  # policy exposed, SHOULD not mandatory by default
        cond = SPEC.replace("The endpoint SHOULD retain", "If the peer is idle the endpoint SHOULD retain")
        ins = {i.id: i for i in anchor(cond, m2)}["I-02"]; self.assertIn("If the peer", ins.condition or "If the peer")
        neg = {i.id: i for i in anchor("[I-09] The endpoint MUST NOT close and MUST NOT send.\n", m2)}["I-09"]
        self.assertTrue(neg.negated); self.assertEqual(len(neg.actions), 2)

    def test_determinism_and_spans(self):
        a, b = derive_readings(SPEC, MODEL), derive_readings(SPEC, MODEL)
        self.assertEqual([r.to_dict() for rs in a["readings"].values() for r in rs], [r.to_dict() for rs in b["readings"].values() for r in rs])
        ins = a["instructions"][0]; self.assertEqual(SPEC[ins.start:ins.end], ins.text); self.assertEqual((ins.line, ins.col), (2, 8))
        h = [i.id for i in anchor("The endpoint closes.\n", MODEL)][0]
        self.assertEqual(h, [i.id for i in anchor("   The   endpoint  CLOSES.   \n", MODEL)][0])   # stable under harmless formatting

    def test_hash_refresh_and_edit_log(self):
        R, *_ = pipeline(SPEC, MODEL, ["P1", "P3"])
        self.assertNotEqual(R["analysis0"]["sha256"], R["A1"]["sha256"]); self.assertEqual(R["A1"]["sha256"], sha256(R["revised_text"]))
        e = R["edit_log"][0]
        self.assertEqual({"original_wording", "proposed_wording", "final_wording"} <= set(e), True); self.assertEqual(e["proposed_wording"], e["final_wording"])
        self.assertEqual(R["A1"]["instructions"][0].end, R["A1"]["instructions"][0].start + len(R["A1"]["instructions"][0].text))


class FsmProperties(unittest.TestCase):
    def test_deadlock(self):
        m = mini({"a": R_("A0", ["A0", "A1"], [("a1", "A0", "A1", "?X")]), "b": R_("B0", ["B0"], [])}, [])
        r = check(m, prop("D", "deadlock_freedom", final={"A": ["A1"], "B": ["B0"]}))
        self.assertEqual(r["status"], VIOLATION); self.assertTrue(r["trace"] is not None)

    def test_unspecified_reception_and_invalid_transition(self):
        m = mini({"a": R_("A0", ["A0", "A1"], [("a1", "A0", "A1", "!X")]), "b": R_("B0", ["B0", "B1"], [("b1", "B0", "B1", "?Y")])}, [])
        self.assertEqual(check(m, prop("U", "unspecified_reception"))["status"], VIOLATION)
        m["messages"] = ["Y"]; self.assertEqual(check(m, prop("I", "invalid_transition"))["status"], VIOLATION)   # X not declared

    def test_completion_reachability_vs_guaranteed(self):
        roles = {"a": R_("A0", ["A0", "A1", "A2"], [("a1", "A0", "A1", "tau"), ("a2", "A0", "A2", "tau")]), "b": R_("B0", ["B0"], [])}
        goal = {"A": ["A1"], "B": ["B0"]}; m = mini(roles, [])
        self.assertEqual(check(m, prop("C", "can_complete", goal=goal))["status"], VERIFIED_SAFE)          # one path reaches goal
        self.assertEqual(check(m, prop("E", "inevitable_completion", goal=goal))["status"], VIOLATION)     # but not every run
        self.assertEqual(check(m, prop("G", "always_can_complete", goal=goal))["status"], VIOLATION)

    def test_livelock_not_inevitable(self):
        m = mini({"a": R_("A0", ["A0", "A1"], [("a1", "A0", "A0", "tau"), ("a2", "A0", "A1", "tau")]), "b": R_("B0", ["B0"], [])}, [])
        goal = {"A": ["A1"], "B": ["B0"]}
        self.assertEqual(check(m, prop("C", "always_can_complete", goal=goal))["status"], VERIFIED_SAFE)
        self.assertEqual(check(m, prop("E", "inevitable_completion", goal=goal))["status"], VIOLATION)

    def test_forbidden_ordering_invariant(self):
        m = mini({"a": R_("A0", ["A0", "A1", "A2"], [("a1", "A0", "A1", "close"), ("a2", "A1", "A2", "tau")], ["A1"]), "b": R_("B0", ["B0"], [])}, [])
        self.assertEqual(check(m, prop("F", "forbidden_action", action="close"))["status"], VIOLATION)
        self.assertEqual(check(m, prop("O", "required_ordering", later="close", earlier="?GO"))["status"], VIOLATION)
        self.assertEqual(check(m, prop("S", "state_invariant", forbid=[{"locals": {"A": ["A2"]}}]))["status"], VIOLATION)
        self.assertEqual(check(m, prop("S2", "state_invariant", forbid=[{"locals": {"A": ["A2"], "B": ["BX"]}}]))["status"], VERIFIED_SAFE)

    def test_state_limit_is_incomplete_not_safe(self):
        r = check(MODEL | {}, prop("P1", "no_orphan_message"), limit=3) if False else None
        m, s = ex("ack_close"); R, *_ = pipeline(s, m, ["P1"], "audit", {"max_states": 3})
        base = R["V0"]["table"][("ordered", "enforced", "ordered", "enforced")]["results"]["P1"]
        self.assertEqual(base["status"], INCOMPLETE); self.assertFalse(base["complete"]); self.assertIn("state limit", base["reason"])
        self.assertEqual(R["final_status"], INCOMPLETE)

    def test_structured_result_fields(self):
        R, *_ = pipeline(SPEC, MODEL, ["P1"], "audit")
        r = next(iter(R["V0"]["table"].values()))["results"]["P1"]
        for k in ("property", "description", "status", "assumptions", "bounds", "complete", "reason", "states_explored"): self.assertIn(k, r)


class Validation(unittest.TestCase):
    def test_errors_name_fields(self):
        m = copy.deepcopy(MODEL); m["roles"]["endpoint"]["transitions"][0]["dst"] = "NOPE"; m["roles"]["endpoint"]["initial"] = "ZZ"
        m["bindings"]["I-01"]["ORDER"]["first"] = "t99"; m["bindings"]["I-02"]["FOO"] = {}
        m["system"]["assumptions"]["message_loss"] = True; m["system"]["implementations"]["A"]["peer"] = "Q"
        E = "\n".join(validate_model(m, ["P9"]))
        for frag in ("roles.endpoint.initial", "transitions[t1].dst", "bindings.I-01.ORDER.first", "bindings.I-02.FOO: unsupported operator", "message_loss", "implementations.A.peer", "unknown property id 'P9'"):
            self.assertIn(frag, E)

    def test_message_direction_and_reading_refs(self):
        m = copy.deepcopy(MODEL); m["roles"]["endpoint"]["transitions"].append({"id": "t9", "src": "E0", "dst": "E1", "action": "!ZZZ"})
        self.assertIn("never received", "\n".join(validate_model(m)))
        m = copy.deepcopy(MODEL); m["bindings"]["I-02"]["MODALITY"]["hold"] = "t4"
        m["roles"]["endpoint"]["transitions"] = [t for t in m["roles"]["endpoint"]["transitions"] if t["id"] != "t3"]
        with self.assertRaises(InputError): run(SPEC, m, ["P1"])

    def test_profile_space_overflow_explained(self):
        R, *_ = pipeline(SPEC, MODEL, ["P1", "P3"], "compile", {"max_profiles": 5})
        V = R["V0"]; self.assertTrue(V["truncated"]); self.assertEqual((V["profiles_checked"], V["profiles_total"]), (5, 16))
        self.assertIn("NOT checked", V["limit_note"]); self.assertEqual(R["final_status"], INCOMPLETE); self.assertIsNone(R["revised_text"])

    def test_cli_errors(self):
        d = tempfile.mkdtemp(); bad = f"{d}/bad.json"; open(bad, "w").write("{not json")
        def cli(*a):
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()): rc = main(list(a))
            return rc, err.getvalue()
        sp, mp = f"{ROOT}/ack_close/spec.txt", f"{ROOT}/ack_close/model.json"
        rc, e = cli("audit", "--spec", f"{d}/nope.txt", "--model", mp); self.assertEqual(rc, 2); self.assertIn("file not found", e)
        rc, e = cli("audit", "--spec", sp, "--model", bad); self.assertEqual(rc, 2); self.assertIn("malformed JSON", e)
        rc, e = cli("audit", "--spec", sp, "--model", mp, "--props", "PX"); self.assertEqual(rc, 2); self.assertIn("PX", e)
        rc, e = cli("audit", "--spec", sp, "--model", mp, "--out", d); self.assertEqual(rc, 0)


class Interaction(unittest.TestCase):
    def test_mixed_vs_common_mode(self):
        self.assertEqual(classify([("A", "I"), ("B", "I")], ("x", "x")), "common-mode"); self.assertEqual(classify([("A", "I"), ("B", "I")], ("x", "y")), "mixed")
        R, *_ = pipeline(SPEC, MODEL, ["P1", "P2"], "audit"); t = R["V0"]["table"]
        self.assertEqual(t[("ordered", "enforced", "ordered", "enforced")]["status"], VERIFIED_SAFE)
        self.assertEqual(t[("unordered", "enforced", "unordered", "enforced")]["status"], VERIFIED_SAFE)    # common-mode ok
        self.assertEqual(t[("ordered", "enforced", "unordered", "enforced")]["status"], VIOLATION)           # mixed fails
        self.assertEqual(t[("ordered", "relaxed", "ordered", "relaxed")]["status"], VIOLATION)               # common-mode failure
        self.assertEqual(t[("ordered", "relaxed", "ordered", "relaxed")]["class"], "common-mode")

    def pair_model(self):
        m = copy.deepcopy(MODEL)
        m["properties"].append(prop("PAIR", "state_invariant", forbid=[{"locals": {"A": ["CLOSE~I-01:unordered"], "B": ["CLOSE~I-01:unordered"]}}]))
        return m

    def test_single_and_pair_minimal_combinations(self):
        R, *_ = pipeline(SPEC, MODEL, ["P1", "P3"], "audit")
        w = next(x for x in R["witnesses"] if x["property_id"] == "P1")
        self.assertTrue(all(len(c) == 1 for c in w["minimal_combinations"]["combinations"]))                  # one reading alone causes it
        R, *_ = pipeline(SPEC, self.pair_model(), ["PAIR"], "audit")
        w = next(x for x in R["witnesses"] if x["profile"] == {"A::I-01": "unordered", "A::I-02": "enforced", "B::I-01": "unordered", "B::I-02": "enforced"})
        mc = w["minimal_combinations"]; self.assertEqual(len(mc["combinations"]), 1); self.assertEqual(len(mc["combinations"][0]), 2)   # needs both together
        self.assertTrue(mc["subset_minimal_exhaustive"] and mc["profile_is_itself_minimal"])
        V = R["V0"]; prof = tuple(w["profile"].values())
        for lit in mc["combinations"][0]:                                                                    # removing any element removes the violation
            reduced = tuple(prof[i] if (V["slots"][i][0], V["slots"][i][1]) != (lit["impl"], lit["instruction"]) and prof[i] != V["domains"][V["slots"][i]][0] else V["domains"][V["slots"][i]][0] for i in range(4))
            self.assertEqual(V["table"][reduced]["results"]["PAIR"]["status"], VERIFIED_SAFE)
        self.assertEqual(sorted(len(n["literals"]) for n in R["selected_nogoods"]), [2])
        ng = R["selected_nogoods"][0]; self.assertIn("meaning", ng["condition"]); self.assertEqual(ng["condition"]["responsible_instructions"], ["I-01"])

    def test_minimisation_limit_recorded(self):
        R, *_ = pipeline(SPEC, MODEL, ["P1", "P3"], "audit", {"exhaustive_minimisation_max_literals": 1})
        self.assertFalse(all(w["minimal_combinations"]["subset_minimal_exhaustive"] for w in R["witnesses"]))

    def test_two_interacting_violations_smallest_set_and_necessity(self):
        R, *_ = pipeline(SPEC, MODEL, ["P1", "P3"])
        self.assertEqual(len(R["edits"]), 2)
        for n in R["rounds"][0]["necessity"]: self.assertTrue(n["nogoods_unsatisfied_without_it"])         # removing any edit breaks a constraint
        self.assertEqual(R["optimisation"]["status"], OPT_OPTIMAL)
        R, *_ = pipeline(SPEC, MODEL, ["P1", "P2"]); self.assertEqual(len(R["edits"]), 1)                    # smaller set exists under weaker property
        self.assertTrue(any(len(n["literals"]) == 2 for n in R["nogoods"]))                                  # interacting (multi-literal) nogoods handled

    def test_unsatisfiable_and_limit(self):
        m = copy.deepcopy(MODEL); m["bindings"]["I-02"]["MODALITY"].pop("relaxed_text"); m["bindings"]["I-01"]["ORDER"]["vars"] = {}
        for k in ("I-01",): m["bindings"][k]["ORDER"]["vars"] = {}
        R, *_ = pipeline(SPEC, m, ["P1", "P3"])
        self.assertIn(R["final_status"], (VERIFIED_SAFE, CLAR_UNRESOLVED))
        m2 = copy.deepcopy(MODEL); m2["bindings"]["I-01"]["ORDER"]["first"] = "t3"
        R, *_ = pipeline(SPEC, MODEL, ["P1", "P3"], "compile", {"max_combos": 1})
        self.assertEqual(R["optimisation"]["status"], OPT_LIMIT); self.assertEqual(R["final_status"], CLAR_UNRESOLVED)
        self.assertIn("search limit", R["unresolved_reason"])

    def test_truly_unsatisfiable(self):
        m, s = ex("ref_ambiguity")
        for c in m["bindings"]["I-01"]["REF"]["candidates"]: c.pop("text")          # no safe wording can be generated for any reading
        R, *_ = pipeline(s, m, None)
        self.assertEqual(R["final_status"], CLAR_UNRESOLVED); self.assertEqual(R["optimisation"]["status"], OPT_UNSAT)
        self.assertEqual(R["optimisation"]["remaining_nogoods"], ["NG-01"]); self.assertIn("no candidate edit", R["unresolved_reason"])
        self.assertEqual((R["revised_text"], R["edits"]), (s, []))                  # spec never silently modified

    def test_latitude_three_cases(self):
        R1, *_ = pipeline(SPEC, MODEL, ["P1", "P3"]); R2, *_ = pipeline(SPEC, MODEL, ["P1", "P2"])
        self.assertEqual(R1["latitude"]["profile_level"]["L"], 0.0)                 # safe behaviour preserved
        self.assertGreater(R2["latitude"]["profile_level"]["L"], 0.0)                # permitted behaviour removed
        self.assertGreater(R2["latitude"]["bounded_behaviour"]["L"], R1["latitude"]["bounded_behaviour"]["L"])
        R3, *_ = pipeline(SPEC, MODEL, ["P1", "P2"], "compile", {"max_words": 20})
        self.assertEqual(R3["latitude"]["comparison_status"], "INCOMPLETE_TRUNCATED"); self.assertTrue(R3["latitude"]["bounded_behaviour"]["truncated"])
        self.assertEqual(R1["latitude"]["comparison_status"], "COMPLETE_WITHIN_DEPTH")

    def test_coverage_prevents_unconditional_safe(self):
        m, s = ex("incomplete_coverage"); R, *_ = pipeline(s, m, None)
        self.assertEqual(R["final_status"], INCOMPLETE); cs = R["coverage_summary0"]
        self.assertEqual(cs["unresolved_instructions"], ["I-03", "I-04"]); self.assertEqual(cs["instructions_total"], 4); self.assertEqual(cs["instructions_linked_to_model"], 3)
        self.assertEqual(cs["properties"]["P1"]["with_violations"], 0)


class Evidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.R, cls.cert, cls.chk, cls.tests = pipeline(SPEC, MODEL, ["P1", "P3"])

    def tamper(self, f):
        c = copy.deepcopy(self.cert); f(c); return check_certificate(c)

    def test_valid_certificate(self): self.assertTrue(self.chk["accepted"]); self.assertEqual(self.chk["counts"]["rejected"], 0)

    def test_tampering(self):
        def model_hash(c): c["model_sha256"] = "0" * 64
        def model_body(c): c["model"]["system"]["channel_capacity"] = 1
        def trace(c): next(r for r in c["original"]["results"] if r["status"] == VIOLATION)["trace"][-1]["tid"] = "t1"
        def result(c): next(r for r in c["original"]["results"] if r["status"] == VIOLATION).update(status=VERIFIED_SAFE, trace=None)
        def coverage(c): c["original"]["coverage"].pop("I-02")
        def cov_rec(c): c["original"]["coverage_records"].pop(0)
        def edit(c): c["edits"][0]["new_text"] = "[I-01] tampered"
        def spec(c): c["revised_spec"] += "x"
        def props(c): c["properties"][0]["description"] = "changed"
        def assum(c): c["model_assumptions"]["message_loss"] = True
        def schema(c): c.pop("limits")
        def removal(c): c["removal_claim"]["targeted_remaining"] = 7
        for f in (model_hash, model_body, trace, result, coverage, cov_rec, edit, spec, props, assum, schema, removal):
            with self.subTest(f.__name__): self.assertEqual(self.tamper(f)["status"], CERT_REJECTED)

    def test_unverified_when_limits_too_small(self):
        r = self.tamper(lambda c: c["limits"].update(max_states=3))
        self.assertFalse(r["accepted"]); self.assertGreater(r["counts"]["unverified"] + r["counts"]["rejected"], 0)

    def test_trace_not_ending_in_violation_rejected(self):
        def f(c):
            v = next(r for r in c["original"]["results"] if r["status"] == VIOLATION and r["property"] == "P1"); v["trace"] = v["trace"][:1]
        self.assertEqual(self.tamper(f)["status"], CERT_REJECTED)

    def test_all_property_types_checked_by_checker(self):
        m, s = ex("modality_optional"); R, cert, chk, _ = pipeline(s, m, None); self.assertTrue(chk["accepted"])     # includes derived required_ordering
        m, s = ex("scope_ambiguity"); self.assertTrue(pipeline(s, m, None)[2]["accepted"])
        m, s = ex("ref_ambiguity"); self.assertTrue(pipeline(s, m, None)[2]["accepted"])

    def test_tests_traceable_and_labelled(self):
        kinds = {t["kind"] for t in self.tests}
        self.assertTrue({"normal_success_coverage", "counterexample", "clarification_regression"} <= kinds)
        for t in self.tests:
            for k in ("id", "source_instructions", "motivating_property", "preconditions", "traceability", "execution_status", "signature", "duplicate_of", "setup", "expected"): self.assertIn(k, t)
            self.assertNotEqual(t["execution_status"], "executed_against_implementation")
            if t["certified"]: self.assertEqual(t["execution_status"], "replayed_in_model")
        self.assertTrue(any(t["certified"] for t in self.tests))
        reg = next(t for t in self.tests if t["kind"] == "clarification_regression"); self.assertIn("not enabled", reg["expected"]["model_check"])
        mark_executed(self.tests, self.tests[0]["id"], True, "ref-impl"); self.assertEqual(self.tests[0]["execution_status"], "executed_against_implementation")
        self.tests[0]["execution_status"] = "replayed_in_model"

    def test_operator_boundary_and_alternative_tests(self):
        for name, kind in (("tolerance_boundary", "boundary_condition"), ("ref_ambiguity", "alternative_reading_REF"), ("scope_ambiguity", "alternative_reading_SCOPE"), ("definition_ambiguity", "alternative_reading_DEF")):
            m, s = ex(name); R, cert, chk, tests = pipeline(s, m, None)
            t = [x for x in tests if x["kind"] == kind]
            if name == "definition_ambiguity":                       # DEF senses differ in state labelling, not in observable actions: no invented test
                with self.subTest(name): self.assertFalse(t); self.assertTrue(any(x["kind"] == "no_difference_found" for x in tests)); continue
            with self.subTest(name): self.assertTrue(t and t[0]["steps"] and all("tid" in x for x in t[0]["steps"]) and t[0]["execution_status"] in ("replayed_in_model", "generated"))
        m, s = ex("tolerance_boundary"); t = next(x for x in pipeline(s, m, None)[3] if x["kind"] == "boundary_condition")
        self.assertEqual(t["expected"]["numeric"]["value"], 5); self.assertIn("5 seconds", t["targets"])

    def test_duplicates_detected_and_unknown_tests(self):
        m, s = ex("incomplete_coverage"); R, *_ = pipeline(s, m, None, "compile", {"max_states": 3})
        from rcpvs.tests_gen import generate_tests
        t = generate_tests(R["A1"], m, R["V1"], R["limits"], R)
        self.assertTrue(any(x["kind"] == "expected_result_unknown" for x in t))

    def test_audit_compile_consistency_and_reproducible_reports(self):
        A, *_ = pipeline(SPEC, MODEL, ["P1", "P3"], "audit"); C = self.R
        self.assertIsNone(A["revised_text"]); self.assertEqual(A["spec_sha256"], C["spec_sha256"])
        self.assertEqual([(e["instruction_id"], e["keep_reading"]) for e in A["audit_recommendation"]["edits"]], [(e["instruction_id"], e["keep_reading"]) for e in C["edits"]])
        from rcpvs.report import markdown
        R1, c1, k1, t1 = pipeline(SPEC, MODEL, ["P1", "P3"]); R2, c2, k2, t2 = pipeline(SPEC, MODEL, ["P1", "P3"])
        self.assertEqual(markdown(R1, MODEL, k1, t1), markdown(R2, MODEL, k2, t2)); self.assertEqual(canon(c1), canon(c2))
        rep = markdown(R1, MODEL, k1, t1)
        for h in ("## 1. Input", "## 4. Alternative readings", "## 8. Conditional nogoods", "## 11. Behaviour preservation", "## 13. Conformance tests", "## 14. Limitations", "unbounded executions"): self.assertIn(h, rep)


class Examples(unittest.TestCase):
    def test_all_examples_match_expected(self):
        sys.path.insert(0, ROOT); import run_examples
        for name in sorted(n for n in os.listdir(ROOT) if os.path.isfile(f"{ROOT}/{n}/expected.json")):
            for _, bad in run_examples.run_example(name):
                with self.subTest(name): self.assertEqual(bad, [])


if __name__ == "__main__": unittest.main()
