# Reading-Closure Protocol Verification Studio (RCPVS)

Reference implementation of the disclosed architecture. Pure Python 3.10+, no third-party dependencies.
`CLAIMS_CHECKLIST.md` maps each proposed claim to code, tests, limits and status (an engineering traceability document, not a patentability assessment).
Optional extras (`python-sat`, `z3-solver`) are only needed for `--optimiser maxsat` and `crosscheck`; the core runs on the standard library.
Everything below describes what the code does today; limitations are listed explicitly at the end.

## Install and run
    python -m rcpvs.cli audit   --spec examples/ack_close/spec.txt --model examples/ack_close/model.json --props P1,P2 --out out/audit
    python -m rcpvs.cli compile --spec examples/ack_close/spec.txt --model examples/ack_close/model.json --out out/strict
    python -m rcpvs.cli check   out/strict/certificate.json      # independent checker, exit code 2 if not accepted
    python -m rcpvs.cli dot --model examples/ack_close/model.json --role endpoint
    python -m rcpvs.cli compile ... --optimiser maxsat           # optional; needs: pip install python-sat
    python -m rcpvs.cli crosscheck --spec ... --model ...        # optional; needs: pip install z3-solver
    python case_studies/rfc1122_half_duplex_close/run_case_study.py   # real-source case study + execution on the OS TCP stack
    python examples/build_examples.py && python examples/run_examples.py
    python -W ignore -m unittest discover tests -v                # 188 tests in 11 modules (the SMT tests take ~30 s)
Errors (missing file, malformed JSON, unknown property id, unsupported operator name, invalid state/transition reference,
unsupported communication assumption) are reported with the offending field, exit code 2.

## Modes
* **audit**: analyse, verify, show violations/traces/nogoods, and *recommend* clarifications with an optimiser status. The specification is never changed.
* **compile**: audit + select clarifications under the objective, apply them, re-read the revised text with the same operators, re-verify,
  generate report, certificate, conformance tests, and run the independent checker.

## Modules
| Module | Content |
|---|---|
| `models.py` | data structures, status constants |
| `validate.py` | model/binding/reading validation, explicit communication assumptions |
| `maxsat_opt.py` | optional weighted-MaxSAT optimiser (`--optimiser maxsat`, RC2 from python-sat) |
| `smt_check.py` | Z3 bounded-model-checking cross-check (`crosscheck` command); different method, same author |
| `tolerance.py` | typed numeric constraints (value, unit, comparator, bounds, inclusivity) and boundary probes; not a timed verifier |
| `checker_rules.py` | checker-side reading derivation, written without importing `spec_analysis` |
| `spec_analysis.py` | anchoring (line:col spans, content-hash IDs), operators ORDER/REF/DEF/SCOPE/TOL/MODALITY, interpretation policy, definition table |
| `fsm.py` | patch application, asynchronous FIFO composition, 10 property types, structured results, bounded behaviours |
| `engine.py` | profiles (mixed/common-mode), minimal combinations, nogoods, optimiser, latitude loss, coverage summary, edit log, re-verification |
| `certificate.py` | certificate (schema + hashes), independent checker |
| `tests_gen.py` | conformance tests with traceability and execution status |
| `report.py`, `cli.py` | 14-section report, CLI |

## Property types
`no_orphan_message`, `deadlock_freedom`, `unspecified_reception`, `invalid_transition`, `forbidden_action`, `required_ordering`, `state_invariant`
(safety); `can_complete` (reachability only), `always_can_complete` (a goal stays reachable), `inevitable_completion` (every run reaches the goal; detects stuck states and livelock).
A state-limit hit yields INCOMPLETE, never safe. Violations found in a truncated exploration remain sound witnesses.

## Definitions
* **Minimal violating combination**: set S of non-baseline readings whose profile (rest at baseline) violates, with no proper subset doing so.
  Recorded together with whether minimisation was exhaustive.
* **Conditional nogood**: prime implicant of the violating-profile set over the enumerated profile space; valid only under the recorded assumptions.
* **Optimiser objective**: hit every nogood > fewest edits > least latitude loss > shortest, source-aligned wording. Status OPTIMAL / UNSATISFIABLE / INCOMPLETE_LIMIT_REACHED;
  necessity witnesses show which nogoods fail if any chosen edit is dropped.
* **Latitude loss**: reported separately at profile level and as bounded-depth event words (depth, cap, truncation recorded; comparison status COMPLETE_WITHIN_DEPTH or INCOMPLETE_TRUNCATED).
* **Test status**: generated -> replayed_in_model (independent checker) -> executed_against_implementation (only via `mark_executed`, an external run).

## Examples (`examples/*/`: spec, model, expected.json, README)
ack_close, ref_ambiguity, scope_ambiguity, definition_ambiguity, tolerance_boundary, modality_optional, mixed_deployment, common_mode, multi_violation, incomplete_coverage.
These are engineered mechanism tests, not experiments on real protocols.

## Case study, semantics, review
* `case_studies/rfc1122_half_duplex_close/`: RFC 1122 §4.2.2.13 (author's paraphrase and abstraction, traceable sources, outputs, results, execution against the real TCP stack). Read `RESULTS.md` limits first.
* `docs/SEMANTICS.md` is the reference for independent re-implementation; `docs/REVIEW_PACKAGE.md` prepares an independent review (none has been done).
* n-party models: addressed sends `!M@X`, one FIFO mailbox per implementation (sender identity not tracked), tested with 3 implementations.

## Known limitations (do not hide these in the disclosure)
* Instruction-to-FSM bindings are supplied by the model author; there is no automatic text-to-FSM extraction.
* Operators are cue/regex based and only handle the documented patterns; everything else is UNANALYSED. MUST NOT is only modelled when a prohibition is bound.
* Only asynchronous, reliable, bounded FIFO channels are supported (others are rejected by validation). Results are not proofs for unbounded executions.
* Profile space is enumerated exhaustively up to `max_profiles`; beyond that no clarification is attempted and the status is INCOMPLETE.
* The default optimiser is exact bounded enumeration (an opt-in weighted-MaxSAT mode exists and agrees on all fixtures) over per-instruction edits (keep-one-reading, exclude-one-reading with author-supplied wording); it is not MaxSAT.
  Wording for edits is template/author-supplied, so edits exist only where such wording exists.
* Property policy for the revised spec: original properties are always held constant; properties newly derived from the revised text (e.g. an introduced MUST NOT) are checked in addition (`property_policy: rederive`, default) or listed as not checked (`original`). The report lists held / added / changed / removed properties.
* TOL attaches typed constraints to readings and `tolerance.py` evaluates concrete values against them, but the FSM verifier only sees the boundary as one discrete transition: this is not general numeric or timed verification.
* The checker derives readings with its own code (`checker_rules.py`) and has its own composition, property evaluation, replay, hashes and schema checks. It still shares documented conventions with the engine (model/binding schema, patch-operation semantics, rule-set version) and is written by the same author; a differential test and 20+ tamper tests exist, but a flaw present in both implementations would not be caught.
* Operator conformance tests are generated only when readings differ observably within the depth bound; otherwise a `no_difference_found` record is produced. Nothing is ever marked executed against a real implementation by the tool itself.
