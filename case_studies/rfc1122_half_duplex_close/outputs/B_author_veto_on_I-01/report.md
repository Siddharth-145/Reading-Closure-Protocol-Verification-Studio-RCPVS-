# Protocol Verification Report — RFC 1122 4.2.2.13 half-duplex close (author's abstraction)
_Reading-Closure Protocol Verification Studio. Engineered examples are illustrative, not evidence from real protocols._

## 1. Input specification
- Mode: **compile**; source SHA-256 `cfb46a000cdf54f032b41d8c06306db17f60758ec132406ca625c414c24cfebb`; rule set `2.0.0`
- Original status: **VIOLATION_FOUND**; final status: **VERIFIED_SAFE_WITHIN_SCOPE**

## 2. Model description and assumptions
- Communication: asynchronous, channels FIFO, message loss allowed: False, channel capacity 2
- Exploration bound: max_states 100000, max_profiles 5000. Results hold for these bounded FIFO channels only; they are NOT proofs for unbounded executions.
- Roles: sender, receiver; implementations: S(sender), R(receiver)
- Interpretation policy: {'MUST': 'enforced', 'SHOULD': 'both_readings', 'MAY': 'both_readings', 'MUST NOT': 'derived_safety_property'}

## 3. Reading operators and coverage
| Instruction | Line:Col | Rule | Status | Reason |
|---|---|---|---|---|
| I-01 | 2:8 | MOD-1 | ANALYSED | MAY: permitted optional path and no-optional-action path both represented |
| I-02 | 3:8 | MOD-1 | ANALYSED | SHOULD admits enforced and relaxed readings |

## 4. Alternative readings linked to source
| Instruction | Reading | Rule | Cue span | Affected | Preconditions |
|---|---|---|---|---|---|
| I-01 | omitted | MOD-1@2.0.0 | (7, 10) | [] | ['modality=MAY', 'policy=both_readings', 'multi-action sentence: relaxation applies to the bound behaviour only'] |
| I-01 | implemented | MOD-1@2.0.0 | (7, 10) | ['r4'] | ['modality=MAY', 'policy=both_readings', 'multi-action sentence: relaxation applies to the bound behaviour only'] |
| I-02 | enforced | MOD-1@2.0.0 | (101, 107) | [] | ['modality=SHOULD', 'policy=both_readings', 'conditional: If a host with half-duplex close closes the connection while received data is still pending, its TCP SHOULD send a reset to show the data was lost.'] |
| I-02 | relaxed | MOD-1@2.0.0 | (101, 107) | ['r5'] | ['modality=SHOULD', 'policy=both_readings', 'conditional: If a host with half-duplex close closes the connection while received data is still pending, its TCP SHOULD send a reset to show the data was lost.'] |

## 5. Deployment profiles analysed
Checked 4 of 4 profiles (1 violating, 3 safe, 0 incomplete).

| Profile | Class | R::I-01 | R::I-02 | Status |
|---|---|---|---|---|
| P1 | common-mode | implemented | enforced | VERIFIED_SAFE_WITHIN_SCOPE |
| P2 | common-mode | implemented | relaxed | VIOLATION_FOUND |
| P3 | common-mode | omitted | enforced | VERIFIED_SAFE_WITHIN_SCOPE |
| P4 | common-mode | omitted | relaxed | VERIFIED_SAFE_WITHIN_SCOPE |

## 6. Property results
### Coverage summary (original)
- Instructions: 2 total, 2 linked to the model; unresolved: none
- Analysed by operator: MOD-1: ['I-01', 'I-02']
- Profiles checked: 4 of 4; limits reached: {'profile_enumeration': False, 'state_limit': False}

| Property | profiles safe | with violations | not fully checked |
|---|---|---|---|
| P1 | 3 | 1 | 0 |
| P2 | 4 | 0 | 0 |

## 7. Counterexamples and causes
**P1** (forbidden state invariant violated) violated by common-mode profile `{'R::I-01': 'implemented', 'R::I-02': 'relaxed'}`.
Minimal violating combinations (no proper subset of a listed combination, with all other slots at baseline, reproduces this violation; exhaustive=True, this profile itself minimal=True): [[{'impl': 'R', 'instruction': 'I-01', 'reading': 'implemented'}, {'impl': 'R', 'instruction': 'I-02', 'reading': 'relaxed'}]]

- I-01 (line 2, col 8): “A host MAY implement a half-duplex close, after which the application cannot read further data.” → reading `implemented` (optional behaviour implemented); affected ['r4']; rule MOD-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)
- I-01 (line 2, col 8): “A host MAY implement a half-duplex close, after which the application cannot read further data.” → reading `implemented` (optional behaviour implemented); affected ['r4']; rule MOD-1@2.0.0; transition tagged I-01:implemented occurs in the counterexample trace
- I-02 (line 3, col 8): “If a host with half-duplex close closes the connection while received data is still pending, its TCP SHOULD send a reset to show the data was lost.” → reading `relaxed` (treated as optional / bypassable); affected ['r5']; rule MOD-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)
- I-02 (line 3, col 8): “If a host with half-duplex close closes the connection while received data is still pending, its TCP SHOULD send a reset to show the data was lost.” → reading `relaxed` (treated as optional / bypassable); affected ['r5']; rule MOD-1@2.0.0; transition tagged I-02:relaxed occurs in the counterexample trace

| Step | Impl | Action | Transition | Reading tag | state R | state S |
|---|---|---|---|---|---|---|
| 1 | S | `!DATA` | s1 | base | R0 | S1 |
| 2 | R | `?DATA` | r1 | base | R1 | S1 |
| 3 | R | `close` | r4 | I-01:implemented | R3 | S1 |
| 4 | R | `!FIN` | r5 | I-02:relaxed | R4 | S1 |
| 5 | S | `?FIN` | s3 | base | R4 | S3 |

## 8. Conditional nogoods (selected irredundant cover)
- NG-01: forbid [('R', 'I-01', 'implemented'), ('R', 'I-02', 'relaxed')] (instructions ['I-01', 'I-02']; properties ['P1']; assumptions `cf133e4621f835b2`). Irredundancy witness: `{'R::I-01': 'implemented', 'R::I-02': 'relaxed'}`. Meaning: these readings must not remain simultaneously possible.

## 9. Candidate clarifications and optimisation objective
Objective (lexicographic): hit every nogood > fewest edits > least latitude loss > shortest, source-aligned wording.
Candidates: [('I-01', 'change-constraint-strength', 'implemented'), ('I-02', 'change-constraint-strength', 'enforced'), ('I-02', 'change-constraint-strength', 'relaxed')]
Optimiser: **OPTIMAL**; explored 6 of a search space of 6 candidate edit sets (0 explored = solver-based, no enumeration); optimality proved within the search space: True; remaining nogoods []; None
Objective: 1. hit every nogood (hard constraint; admitted profiles must exclude all violating profiles and be non-empty) 2. minimise number of edits 3. minimise permitted-behaviour (safe-profile) loss 4. minimise total wording length, then number of non-source-aligned edits
Tie-breaking: tuples compared lexicographically; first-found wins exact ties (deterministic candidate order). This is bounded exact enumeration, not MaxSAT.

## 10. Revised specification and re-verification
Revised SHA-256 `e8a0ba6db4f375f95ae69b9e56f536e62e5bc95a2430ae77e462576547b60089`; re-verification status **VERIFIED_SAFE_WITHIN_SCOPE**.
- I-02 [change-constraint-strength] line 3:8: original “If a host with half-duplex close closes the connection while received data is still pending, its TCP SHOULD send a reset to show the data was lost.” → proposed “If a host with half-duplex close closes the connection while received data is still pending, its TCP MUST send a reset to show the data was lost.” → final (re-read) “If a host with half-duplex close closes the connection while received data is still pending, its TCP MUST send a reset to show the data was lost.”
- round 1: status VERIFIED_SAFE_WITHIN_SCOPE; optimiser OPTIMAL; necessity [{'edit': 'I-02:enforced', 'nogoods_unsatisfied_without_it': ['NG-01']}]

**Property policy `rederive`** — held constant (original properties, never replaced): ['P1', 'P2']; added from the revised text: []; changed: []; no longer derivable from the revised text: []; not checked: []
### Coverage summary (revised)
- Instructions: 2 total, 2 linked to the model; unresolved: none
- Analysed by operator: MOD-1: ['I-01', 'I-02']
- Profiles checked: 2 of 2; limits reached: {'profile_enumeration': False, 'state_limit': False}

| Property | profiles safe | with violations | not fully checked |
|---|---|---|---|
| P1 | 2 | 0 | 0 |
| P2 | 2 | 0 | 0 |
Targeted violating profiles still possible after re-reading: 0; P_F(T') size 2, all verified safe: True

## 11. Behaviour preservation (latitude loss)
Universe: original specification's enumerated profile space under the same model.system assumptions (channels, bounds, state limit). Permitted before: profiles verified safe against all selected properties in the original specification; behaviours = event words of those profiles.
- Behaviour: a behaviour is an event word: the ordered sequence of (implementation, action) pairs of one run prefix. Observation rules: identical before and after: same event-word definition, same depth k, same word cap, same state limit, same model.system.
- Profile level (DEFINED): 1/3 = 0.3333333333333333
- Trace level (DEFINED; depth k=10, word cap 20000, truncated=False): 0/9 = 0.0. Bounded-depth counts are NOT a comparison of every possible execution.
- Comparison status: **COMPLETE_WITHIN_DEPTH**. profile-level and trace-level losses are separate measures; trace-level counts depend on depth k and never cover all executions

## 12. Independent checker
Result: **CERTIFICATE_ACCEPTED** — {'verified': 48, 'rejected': 0, 'unverified': 0}. The checker shares only the reading-rule library (rule set 2.0.0) with the engine.

## 13. Conformance tests and execution status
generated = produced from the model; replayed_in_model = independently replayed by the checker; executed_against_implementation = only via an external run (none here).
| ID | Kind | Status | Property | Source instr. | Duplicate of | Target |
|---|---|---|---|---|---|---|
| CT-001 | normal_success_coverage | executed_against_implementation | P1,P2 | ['I-01', 'I-02'] | None | covers transition r1 |
| CT-002 | normal_success_coverage | executed_against_implementation | P1,P2 | ['I-01', 'I-02'] | None | covers transition r2 |
| CT-003 | normal_success_coverage | executed_against_implementation | P1,P2 | ['I-01', 'I-02'] | None | covers transition r3 |
| CT-004 | normal_success_coverage | executed_against_implementation | P1,P2 | ['I-01'] | None | covers transition r4 |
| CT-005 | normal_success_coverage | executed_against_implementation | P1,P2 | ['I-01'] | None | covers transition r5 |
| CT-006 | normal_success_coverage | executed_against_implementation | P1,P2 | ['I-01', 'I-02'] | CT-001 | covers transition r1 |
| CT-007 | normal_success_coverage | executed_against_implementation | P1,P2 | ['I-01', 'I-02'] | CT-002 | covers transition r2 |
| CT-008 | normal_success_coverage | executed_against_implementation | P1,P2 | ['I-01', 'I-02'] | CT-003 | covers transition r3 |
| CT-009 | distinguishing_safe_alternatives | replayed_in_model | None | ['I-01'] | None | distinguishes reading omitted vs implemented of I-01 for R |
| CT-010 | counterexample | executed_against_implementation | P1 | ['I-01', 'I-02'] | None | reproduces counterexample for P1 |
| CT-011 | clarification_regression | executed_against_implementation | P1 | ['I-01', 'I-02'] | None | clarification intended to remove the P1 violation |

## 14. Limitations
- Safe means safe within the stated model, bounds and coverage; UNANALYSED instructions are never treated as unambiguous.
- Instruction-to-FSM bindings are model-author supplied; operators are cue/regex based; the optimiser is exact bounded enumeration, not MaxSAT.
- No claim about real implementations; generated tests are not evidence that any implementation passed them.