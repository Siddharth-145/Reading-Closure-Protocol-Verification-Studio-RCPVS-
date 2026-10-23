"""Final report (14 sections, Part 2 format) + Graphviz export. Statuses are never reduced to pass/fail."""
from __future__ import annotations
from .engine import bad_safe


def _trace_md(trace):
    if not trace: return "_(empty trace: the property fails already in the initial state)_"
    names = sorted(trace[0]["locals"])
    rows = ["| Step | Impl | Action | Transition | Reading tag | " + " | ".join(f"state {n}" for n in names) + " |", "|---|---|---|---|---|" + "---|" * len(names)]
    for s in trace: rows.append(f"| {s['step']} | {s['impl']} | `{s['action']}` | {s['tid']} | {s['reading']} | " + " | ".join(s["locals"][n] for n in names) + " |")
    return "\n".join(rows)


def _cov_md(cs, title):
    o = [f"### {title}", f"- Instructions: {cs['instructions_total']} total, {cs['instructions_linked_to_model']} linked to the model; unresolved: {cs['unresolved_instructions'] or 'none'}",
         f"- Analysed by operator: " + (", ".join(f"{k}: {v}" for k, v in cs["analysed_by_operator"].items()) or "none"),
         f"- Profiles checked: {cs['profiles_checked']} of {cs['profiles_total']}; limits reached: {cs['limits_reached']}", "",
         "| Property | profiles safe | with violations | not fully checked |", "|---|---|---|---|"]
    return o + [f"| {k} | {v['checked_successfully']} | {v['with_violations']} | {v['not_fully_checked']} |" for k, v in cs["properties"].items()]


def markdown(R, model, check=None, tests=None):
    V0, A0, A1 = R["V0"], R["analysis0"], R["A1"]
    bad, safe, inc = bad_safe(V0); sysm = model["system"]; a = sysm["assumptions"]
    o = [f"# Protocol Verification Report — {model.get('name','')}", "_Reading-Closure Protocol Verification Studio. Engineered examples are illustrative, not evidence from real protocols._", "",
         "## 1. Input specification",
         f"- Mode: **{R['mode']}**; source SHA-256 `{R['spec_sha256']}`; rule set `{A0['rule_set_version']}`",
         f"- Original status: **{R['status_original']}**; final status: **{R['final_status']}**", "",
         "## 2. Model description and assumptions",
         f"- Communication: {a['communication']}, channels {a['channels']}, message loss allowed: {a['message_loss']}, channel capacity {sysm['channel_capacity']}"
         + (f" (defaulted: {a['defaulted']})" if a.get("defaulted") else ""),
         f"- Exploration bound: max_states {R['limits']['max_states']}, max_profiles {R['limits']['max_profiles']}. Results hold for these bounded FIFO channels only; they are NOT proofs for unbounded executions.",
         f"- Roles: {', '.join(model['roles'])}; implementations: {', '.join(f'{k}({v['role']})' for k, v in sysm['implementations'].items())}",
         f"- Interpretation policy: {A0['policy']}", "",
         "## 3. Reading operators and coverage", "| Instruction | Line:Col | Rule | Status | Reason |", "|---|---|---|---|---|"]
    ins = {i.id: i for i in A0["instructions"]}
    o += [f"| {c.instruction_id} | {ins[c.instruction_id].line}:{ins[c.instruction_id].col} | {c.rule_id} | {c.status} | {c.reason} |" for c in A0["coverage"] if c.status != "INAPPLICABLE"]
    if A0["definition_table"]: o += ["", "Definition table: " + "; ".join(f"{d['term']} → {d['candidates']} (source {d['source']}, affects {d['affected_instructions']})" for d in A0["definition_table"])]
    o += ["", "## 4. Alternative readings linked to source", "| Instruction | Reading | Rule | Cue span | Affected | Preconditions |", "|---|---|---|---|---|---|"]
    for iid, rs in A0["readings"].items():
        for r in rs: o.append(f"| {iid} | {r.reading_id} | {r.rule_id}@{r.rule_version} | {r.cue_span} | {[x['id'] for x in r.affected]} | {r.preconditions} |")
    o += ["", "## 5. Deployment profiles analysed", f"Checked {V0['profiles_checked']} of {V0['profiles_total']} profiles ({len(bad)} violating, {len(safe)} safe, {len(inc)} incomplete)."]
    if V0.get("limit_note"): o.append(f"**LIMIT:** {V0['limit_note']}")
    o += ["", "| Profile | Class | " + " | ".join(f"{x}::{y}" for x, y in V0["slots"]) + " | Status |", "|---|---|" + "---|" * (len(V0["slots"]) + 1)]
    for i, (pr, rec) in enumerate(sorted(V0["table"].items()), 1): o.append(f"| P{i} | {rec['class']} | " + " | ".join(pr) + f" | {rec['status']} |")
    o += ["", "## 6. Property results"] + _cov_md(R["coverage_summary0"], "Coverage summary (original)")
    o += ["", "## 7. Counterexamples and causes"]
    seen = set()
    for w in R["witnesses"]:
        key = (w["property_id"], str(w["minimal_combinations"]["combinations"]))
        if key in seen: continue
        seen.add(key)
        mc = w["minimal_combinations"]
        o += [f"**{w['property_id']}** ({w['witness_kind']}) violated by {w['class']} profile `{w['profile']}`.",
              f"Minimal violating combinations ({mc['definition']}; exhaustive={mc['subset_minimal_exhaustive']}, this profile itself minimal={mc['profile_is_itself_minimal']}): {mc['combinations']}", ""]
        for at in w["attribution"]:
            o.append(f"- {at['instruction']} (line {at['line']}, col {at['col']}): “{at['original_wording']}” → reading `{at['reading']}` ({at['reading_description']}); affected {[x['id'] for x in at['affected']]}; rule {at['rule']}@{at['rule_version']}; {at['contribution']}")
        o += ["", _trace_md(w["trace"]), ""]
        if len(seen) >= 6: o.append("_(further witnesses are in the certificate)_"); break
    o += ["## 8. Conditional nogoods (selected irredundant cover)"]
    for n, wi in zip(R["selected_nogoods"], R["irredundancy"]):
        o.append(f"- {n['id']}: forbid {n['literals']} (instructions {n['condition']['responsible_instructions']}; properties {n['condition']['properties']}; assumptions `{n['condition']['assumptions_id']}`). Irredundancy witness: `{wi['witness_profile']}`. Meaning: {n['condition']['meaning']}.")
    o += ["", "## 9. Candidate clarifications and optimisation objective",
          "Objective (lexicographic): hit every nogood > fewest edits > least latitude loss > shortest, source-aligned wording.",
          f"Candidates: {[(c['instruction_id'], c['operation'], c['keep_reading']) for c in R['candidates']]}"]
    if R.get("optimisation"):
        op = R["optimisation"]
        o += [f"Optimiser: **{op['status']}**; explored {op['candidate_sets_explored']} of a search space of {op['search_space_size']} candidate edit sets (0 explored = solver-based, no enumeration); optimality proved within the search space: {op['optimality_proved_within_search_space']}; remaining nogoods {op['remaining_nogoods']}; {op.get('reason')}",
              "Objective: " + " ".join(op["objective"]), f"Tie-breaking: {op['tie_breaking']}. " + (f"Solver: {op['solver']}." if op.get("solver") else "This is bounded exact enumeration, not MaxSAT.")]
    if R.get("audit_recommendation"):
        o += ["", "### Recommended clarifications (audit mode — for human review; nothing was changed)"] + [f"- **{e['instruction_id']}** [{e['operation']}]: “{e['old_text']}” → “{e['new_text']}”" for e in R["audit_recommendation"]["edits"]]
        o += [f"- necessity: {n}" for n in R["audit_recommendation"]["necessity"]]
    if R.get("rounds") or R.get("edits"):
        o += ["", "## 10. Revised specification and re-verification", f"Revised SHA-256 `{A1['sha256']}`; re-verification status **{R['final_status']}**."]
        for e in R["edit_log"]:
            o.append(f"- {e['instruction_id']} [{e['edit_type']}] line {e['original_span']['line']}:{e['original_span']['col']}: original “{e['original_wording']}” → proposed “{e['proposed_wording']}” → final (re-read) “{e['final_wording']}”")
        for rd in R["rounds"]: o.append(f"- round {rd['round']}: status {rd['status']}; optimiser {rd['optimiser_status']}; necessity {rd['necessity']}")
        pc = R["property_comparison"]
        o += ["", f"**Property policy `{pc['policy']}`** — held constant (original properties, never replaced): {pc['held_constant']}; added from the revised text: {pc['added']}; changed: {pc['changed']}; "
              f"no longer derivable from the revised text: {pc['removed_in_revised_text']}; not checked: {pc['not_checked']}"]
        for p_ in R["revised_properties"]:
            if p_.get("provenance", {}).get("spec_version") == "revised":
                res = [rec["results"][p_["id"]]["status"] for rec in R["V1"]["table"].values()]
                o.append(f"- new property `{p_['id']}` ({p_['type']}) from {p_['instruction']} span {p_['span']} modality {p_['modality']}, revision `{p_['provenance']['revised_sha256'][:12]}…`: results {sorted(set(res))}")
        o += _cov_md(R["coverage_summary1"], "Coverage summary (revised)")
        o.append(f"Targeted violating profiles still possible after re-reading: {len(R['targeted_violations_remaining'])}; P_F(T') size {R['P_F']['size']}, all verified safe: {R['P_F']['all_verified_safe']}")
        L = R["latitude"]; pl, bb = L["profile_level"], L["bounded_behaviour"]
        o += ["", "## 11. Behaviour preservation (latitude loss)", f"Universe: {L['universe']}. Permitted before: {L['permitted_before']}.",
              f"- Behaviour: {L['behaviour_definition']}. Observation rules: {L['observation_rules']}.",
              f"- Profile level ({pl['status']}): {pl['safe_excluded']}/{pl['safe_before']} = {pl['L']}",
              f"- Trace level ({bb['status']}; depth k={bb['depth']}, word cap {bb['word_cap']}, truncated={bb['truncated']}): {bb['V_lost']}/{bb['V_before']} = {bb['L']}. Bounded-depth counts are NOT a comparison of every possible execution.",
              f"- Comparison status: **{L['comparison_status']}**. {L['note']}"]
    if R.get("unresolved_reason"): o += ["", f"**{R['final_status']}**: {R['unresolved_reason']}"]
    if check:
        o += ["", "## 12. Independent checker", f"Result: **{check['status']}** — {check['counts']}. The checker shares only the reading-rule library (rule set {A0['rule_set_version']}) with the engine."]
        o += [f"- {c['verdict']}: {c['claim']} ({c['detail']})" for c in check["claims"] if c["verdict"] != "VERIFIED"]
    if tests:
        o += ["", "## 13. Conformance tests and execution status", "generated = produced from the model; replayed_in_model = independently replayed by the checker; executed_against_implementation = only via an external run (none here).",
              "| ID | Kind | Status | Property | Source instr. | Duplicate of | Target |", "|---|---|---|---|---|---|---|"]
        o_cert = [t for t in tests if t["kind"] == "no_difference_found"]
        o += [f"| {t['id']} | {t['kind']} | {t['execution_status']} | {t['motivating_property']} | {t['source_instructions']} | {t['duplicate_of']} | {t['targets']} |" for t in tests[:40]]
    if tests and o_cert: o += ["", "No distinguishing test was generated for: " + "; ".join(t["targets"] for t in o_cert)]
    o += ["", "## 14. Limitations", "- Safe means safe within the stated model, bounds and coverage; UNANALYSED instructions are never treated as unambiguous.",
          "- Instruction-to-FSM bindings are model-author supplied; operators are cue/regex based; the optimiser is exact bounded enumeration, not MaxSAT.",
          "- No claim about real implementations; generated tests are not evidence that any implementation passed them."]
    return "\n".join(o)


def dot(model, role):
    r = model["roles"][role]
    lines = ["digraph G {", "  rankdir=LR;"]
    for s, f in r["states"].items(): lines.append(f'  "{s}" [shape={"doublecircle" if f.get("closed") else "circle"}];')
    lines += [f'  "{t["src"]}" -> "{t["dst"]}" [label="{t["id"]}: {t["action"]}"];' for t in r["transitions"]]
    return "\n".join(lines + ["}"])
