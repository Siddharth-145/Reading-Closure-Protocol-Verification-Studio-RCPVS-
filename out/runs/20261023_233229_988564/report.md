# Protocol Verification Report — Ack-Close demo (hypothetical)
_Reading-Closure Protocol Verification Studio. Engineered examples are illustrative, not evidence from real protocols._

## 1. Input specification
- Mode: **compile**; source SHA-256 `c9e64bc4c7aad4b76670eb97c42e9172c7bb5fb52a32121fec40110010a52784`; rule set `2.0.0`
- Original status: **VIOLATION_FOUND**; final status: **VERIFIED_SAFE_WITHIN_SCOPE**

## 2. Model description and assumptions
- Communication: asynchronous, channels FIFO, message loss allowed: False, channel capacity 2
- Exploration bound: max_states 100000, max_profiles 5000. Results hold for these bounded FIFO channels only; they are NOT proofs for unbounded executions.
- Roles: endpoint; implementations: A(endpoint), B(endpoint)
- Interpretation policy: {'MUST': 'enforced', 'SHOULD': 'both_readings', 'MAY': 'both_readings', 'MUST NOT': 'derived_safety_property'}

## 3. Reading operators and coverage
| Instruction | Line:Col | Rule | Status | Reason |
|---|---|---|---|---|
| I-01 | 1:8 | ORDER-1 | ANALYSED | conjunction of two events without ordering cue |
| I-02 | 2:8 | MOD-1 | ANALYSED | SHOULD admits enforced and relaxed readings |

## 4. Alternative readings linked to source
| Instruction | Reading | Rule | Cue span | Affected | Preconditions |
|---|---|---|---|---|---|
| I-01 | ordered | ORDER-1@2.0.0 | (47, 82) | [] | ['conjunction without ordering cue', 'binding gives both events'] |
| I-01 | unordered | ORDER-1@2.0.0 | (47, 82) | ['t3'] | ['conjunction without ordering cue', 'binding gives both events'] |
| I-02 | enforced | MOD-1@2.0.0 | (13, 19) | [] | ['modality=SHOULD', 'policy=both_readings'] |
| I-02 | relaxed | MOD-1@2.0.0 | (13, 19) | ['t4'] | ['modality=SHOULD', 'policy=both_readings'] |

## 5. Deployment profiles analysed
Checked 16 of 16 profiles (15 violating, 1 safe, 0 incomplete).

| Profile | Class | A::I-01 | A::I-02 | B::I-01 | B::I-02 | Status |
|---|---|---|---|---|---|---|
| P1 | common-mode | ordered | enforced | ordered | enforced | VERIFIED_SAFE_WITHIN_SCOPE |
| P2 | mixed | ordered | enforced | ordered | relaxed | VIOLATION_FOUND |
| P3 | mixed | ordered | enforced | unordered | enforced | VIOLATION_FOUND |
| P4 | mixed | ordered | enforced | unordered | relaxed | VIOLATION_FOUND |
| P5 | mixed | ordered | relaxed | ordered | enforced | VIOLATION_FOUND |
| P6 | common-mode | ordered | relaxed | ordered | relaxed | VIOLATION_FOUND |
| P7 | mixed | ordered | relaxed | unordered | enforced | VIOLATION_FOUND |
| P8 | mixed | ordered | relaxed | unordered | relaxed | VIOLATION_FOUND |
| P9 | mixed | unordered | enforced | ordered | enforced | VIOLATION_FOUND |
| P10 | mixed | unordered | enforced | ordered | relaxed | VIOLATION_FOUND |
| P11 | common-mode | unordered | enforced | unordered | enforced | VIOLATION_FOUND |
| P12 | mixed | unordered | enforced | unordered | relaxed | VIOLATION_FOUND |
| P13 | mixed | unordered | relaxed | ordered | enforced | VIOLATION_FOUND |
| P14 | mixed | unordered | relaxed | ordered | relaxed | VIOLATION_FOUND |
| P15 | mixed | unordered | relaxed | unordered | enforced | VIOLATION_FOUND |
| P16 | common-mode | unordered | relaxed | unordered | relaxed | VIOLATION_FOUND |

## 6. Property results
### Coverage summary (original)
- Instructions: 2 total, 2 linked to the model; unresolved: none
- Analysed by operator: ORDER-1: ['I-01'], MOD-1: ['I-02']
- Profiles checked: 16 of 16; limits reached: {'profile_enumeration': False, 'state_limit': False}

| Property | profiles safe | with violations | not fully checked |
|---|---|---|---|
| P1 | 5 | 11 | 0 |
| P3 | 1 | 15 | 0 |

## 7. Counterexamples and causes
**P1** (message pending for a closed endpoint) violated by mixed profile `{'A::I-01': 'ordered', 'A::I-02': 'enforced', 'B::I-01': 'ordered', 'B::I-02': 'relaxed'}`.
Minimal violating combinations (no proper subset of a listed combination, with all other slots at baseline, reproduces this violation; exhaustive=True, this profile itself minimal=True): [[{'impl': 'B', 'instruction': 'I-02', 'reading': 'relaxed'}]]

- I-02 (line 2, col 8): “The endpoint SHOULD retain the session until the peer's acknowledgement is received.” → reading `relaxed` (treated as optional / bypassable); affected ['t4']; rule MOD-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)
- I-02 (line 2, col 8): “The endpoint SHOULD retain the session until the peer's acknowledgement is received.” → reading `relaxed` (treated as optional / bypassable); affected ['t4']; rule MOD-1@2.0.0; transition tagged I-02:relaxed occurs in the counterexample trace

| Step | Impl | Action | Transition | Reading tag | state A | state B |
|---|---|---|---|---|---|---|
| 1 | A | `!DATA` | t1 | base | E1 | E0 |
| 2 | B | `!DATA` | t1 | base | E1 | E1 |
| 3 | A | `?DATA` | t2 | base | E2 | E1 |
| 4 | A | `!ACK` | t3 | base | E3 | E1 |
| 5 | B | `?DATA` | t2 | base | E3 | E2 |
| 6 | B | `!ACK` | t3 | base | E3 | E3 |
| 7 | B | `close` | t4'~I-02:relaxed | I-02:relaxed | E3 | CLOSE~I-02:relaxed |

**P3** (state from which the completion goal is unreachable (deadlock/livelock/bad closure)) violated by mixed profile `{'A::I-01': 'ordered', 'A::I-02': 'enforced', 'B::I-01': 'ordered', 'B::I-02': 'relaxed'}`.
Minimal violating combinations (no proper subset of a listed combination, with all other slots at baseline, reproduces this violation; exhaustive=True, this profile itself minimal=True): [[{'impl': 'B', 'instruction': 'I-02', 'reading': 'relaxed'}]]

- I-02 (line 2, col 8): “The endpoint SHOULD retain the session until the peer's acknowledgement is received.” → reading `relaxed` (treated as optional / bypassable); affected ['t4']; rule MOD-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)
- I-02 (line 2, col 8): “The endpoint SHOULD retain the session until the peer's acknowledgement is received.” → reading `relaxed` (treated as optional / bypassable); affected ['t4']; rule MOD-1@2.0.0; transition tagged I-02:relaxed occurs in the counterexample trace

| Step | Impl | Action | Transition | Reading tag | state A | state B |
|---|---|---|---|---|---|---|
| 1 | A | `!DATA` | t1 | base | E1 | E0 |
| 2 | B | `!DATA` | t1 | base | E1 | E1 |
| 3 | A | `?DATA` | t2 | base | E2 | E1 |
| 4 | A | `!ACK` | t3 | base | E3 | E1 |
| 5 | B | `?DATA` | t2 | base | E3 | E2 |
| 6 | B | `!ACK` | t3 | base | E3 | E3 |
| 7 | A | `?ACK` | t4 | base | E4 | E3 |
| 8 | A | `close` | t5 | base | E5 | E3 |
| 9 | B | `close` | t4'~I-02:relaxed | I-02:relaxed | E5 | CLOSE~I-02:relaxed |

**P1** (message pending for a closed endpoint) violated by mixed profile `{'A::I-01': 'ordered', 'A::I-02': 'enforced', 'B::I-01': 'unordered', 'B::I-02': 'enforced'}`.
Minimal violating combinations (no proper subset of a listed combination, with all other slots at baseline, reproduces this violation; exhaustive=True, this profile itself minimal=True): [[{'impl': 'B', 'instruction': 'I-01', 'reading': 'unordered'}]]

- I-01 (line 1, col 8): “After receiving the data message, the endpoint sends an acknowledgement and closes the session.” → reading `unordered` (second event may occur instead of completing the first); affected ['t3']; rule ORDER-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)
- I-01 (line 1, col 8): “After receiving the data message, the endpoint sends an acknowledgement and closes the session.” → reading `unordered` (second event may occur instead of completing the first); affected ['t3']; rule ORDER-1@2.0.0; transition tagged I-01:unordered occurs in the counterexample trace

| Step | Impl | Action | Transition | Reading tag | state A | state B |
|---|---|---|---|---|---|---|
| 1 | A | `!DATA` | t1 | base | E1 | E0 |
| 2 | B | `!DATA` | t1 | base | E1 | E1 |
| 3 | A | `?DATA` | t2 | base | E2 | E1 |
| 4 | A | `!ACK` | t3 | base | E3 | E1 |
| 5 | B | `?DATA` | t2 | base | E3 | E2 |
| 6 | B | `close` | t3'~I-01:unordered | I-01:unordered | E3 | CLOSE~I-01:unordered |

**P3** (state from which the completion goal is unreachable (deadlock/livelock/bad closure)) violated by mixed profile `{'A::I-01': 'ordered', 'A::I-02': 'enforced', 'B::I-01': 'unordered', 'B::I-02': 'enforced'}`.
Minimal violating combinations (no proper subset of a listed combination, with all other slots at baseline, reproduces this violation; exhaustive=True, this profile itself minimal=True): [[{'impl': 'B', 'instruction': 'I-01', 'reading': 'unordered'}]]

- I-01 (line 1, col 8): “After receiving the data message, the endpoint sends an acknowledgement and closes the session.” → reading `unordered` (second event may occur instead of completing the first); affected ['t3']; rule ORDER-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)
- I-01 (line 1, col 8): “After receiving the data message, the endpoint sends an acknowledgement and closes the session.” → reading `unordered` (second event may occur instead of completing the first); affected ['t3']; rule ORDER-1@2.0.0; transition tagged I-01:unordered occurs in the counterexample trace

| Step | Impl | Action | Transition | Reading tag | state A | state B |
|---|---|---|---|---|---|---|
| 1 | A | `!DATA` | t1 | base | E1 | E0 |
| 2 | B | `!DATA` | t1 | base | E1 | E1 |
| 3 | A | `?DATA` | t2 | base | E2 | E1 |
| 4 | A | `!ACK` | t3 | base | E3 | E1 |
| 5 | B | `?DATA` | t2 | base | E3 | E2 |
| 6 | B | `close` | t3'~I-01:unordered | I-01:unordered | E3 | CLOSE~I-01:unordered |

**P1** (message pending for a closed endpoint) violated by mixed profile `{'A::I-01': 'ordered', 'A::I-02': 'enforced', 'B::I-01': 'unordered', 'B::I-02': 'relaxed'}`.
Minimal violating combinations (no proper subset of a listed combination, with all other slots at baseline, reproduces this violation; exhaustive=True, this profile itself minimal=False): [[{'impl': 'B', 'instruction': 'I-01', 'reading': 'unordered'}], [{'impl': 'B', 'instruction': 'I-02', 'reading': 'relaxed'}]]

- I-01 (line 1, col 8): “After receiving the data message, the endpoint sends an acknowledgement and closes the session.” → reading `unordered` (second event may occur instead of completing the first); affected ['t3']; rule ORDER-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)
- I-01 (line 1, col 8): “After receiving the data message, the endpoint sends an acknowledgement and closes the session.” → reading `unordered` (second event may occur instead of completing the first); affected ['t3']; rule ORDER-1@2.0.0; transition tagged I-01:unordered occurs in the counterexample trace
- I-02 (line 2, col 8): “The endpoint SHOULD retain the session until the peer's acknowledgement is received.” → reading `relaxed` (treated as optional / bypassable); affected ['t4']; rule MOD-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)

| Step | Impl | Action | Transition | Reading tag | state A | state B |
|---|---|---|---|---|---|---|
| 1 | A | `!DATA` | t1 | base | E1 | E0 |
| 2 | B | `!DATA` | t1 | base | E1 | E1 |
| 3 | A | `?DATA` | t2 | base | E2 | E1 |
| 4 | A | `!ACK` | t3 | base | E3 | E1 |
| 5 | B | `?DATA` | t2 | base | E3 | E2 |
| 6 | B | `close` | t3'~I-01:unordered | I-01:unordered | E3 | CLOSE~I-01:unordered |

**P3** (state from which the completion goal is unreachable (deadlock/livelock/bad closure)) violated by mixed profile `{'A::I-01': 'ordered', 'A::I-02': 'enforced', 'B::I-01': 'unordered', 'B::I-02': 'relaxed'}`.
Minimal violating combinations (no proper subset of a listed combination, with all other slots at baseline, reproduces this violation; exhaustive=True, this profile itself minimal=False): [[{'impl': 'B', 'instruction': 'I-01', 'reading': 'unordered'}], [{'impl': 'B', 'instruction': 'I-02', 'reading': 'relaxed'}]]

- I-01 (line 1, col 8): “After receiving the data message, the endpoint sends an acknowledgement and closes the session.” → reading `unordered` (second event may occur instead of completing the first); affected ['t3']; rule ORDER-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)
- I-01 (line 1, col 8): “After receiving the data message, the endpoint sends an acknowledgement and closes the session.” → reading `unordered` (second event may occur instead of completing the first); affected ['t3']; rule ORDER-1@2.0.0; transition tagged I-01:unordered occurs in the counterexample trace
- I-02 (line 2, col 8): “The endpoint SHOULD retain the session until the peer's acknowledgement is received.” → reading `relaxed` (treated as optional / bypassable); affected ['t4']; rule MOD-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)

| Step | Impl | Action | Transition | Reading tag | state A | state B |
|---|---|---|---|---|---|---|
| 1 | A | `!DATA` | t1 | base | E1 | E0 |
| 2 | B | `!DATA` | t1 | base | E1 | E1 |
| 3 | A | `?DATA` | t2 | base | E2 | E1 |
| 4 | A | `!ACK` | t3 | base | E3 | E1 |
| 5 | B | `?DATA` | t2 | base | E3 | E2 |
| 6 | B | `close` | t3'~I-01:unordered | I-01:unordered | E3 | CLOSE~I-01:unordered |

_(further witnesses are in the certificate)_
## 8. Conditional nogoods (selected irredundant cover)
- NG-01: forbid [('A', 'I-01', 'unordered')] (instructions ['I-01']; properties ['P1', 'P3']; assumptions `14d1f9fe37285d5b`). Irredundancy witness: `{'A::I-01': 'unordered', 'A::I-02': 'enforced', 'B::I-01': 'ordered', 'B::I-02': 'enforced'}`. Meaning: these readings must not remain simultaneously possible.
- NG-02: forbid [('A', 'I-02', 'relaxed')] (instructions ['I-02']; properties ['P1', 'P3']; assumptions `14d1f9fe37285d5b`). Irredundancy witness: `{'A::I-01': 'ordered', 'A::I-02': 'relaxed', 'B::I-01': 'ordered', 'B::I-02': 'enforced'}`. Meaning: these readings must not remain simultaneously possible.
- NG-03: forbid [('B', 'I-01', 'unordered')] (instructions ['I-01']; properties ['P1', 'P3']; assumptions `14d1f9fe37285d5b`). Irredundancy witness: `{'A::I-01': 'ordered', 'A::I-02': 'enforced', 'B::I-01': 'unordered', 'B::I-02': 'enforced'}`. Meaning: these readings must not remain simultaneously possible.
- NG-04: forbid [('B', 'I-02', 'relaxed')] (instructions ['I-02']; properties ['P1', 'P3']; assumptions `14d1f9fe37285d5b`). Irredundancy witness: `{'A::I-01': 'ordered', 'A::I-02': 'enforced', 'B::I-01': 'ordered', 'B::I-02': 'relaxed'}`. Meaning: these readings must not remain simultaneously possible.

## 9. Candidate clarifications and optimisation objective
Objective (lexicographic): hit every nogood > fewest edits > least latitude loss > shortest, source-aligned wording.
Candidates: [('I-01', 'clarify-event-order', 'ordered'), ('I-01', 'clarify-event-order', 'unordered'), ('I-02', 'change-constraint-strength', 'enforced'), ('I-02', 'change-constraint-strength', 'relaxed')]
Optimiser: **OPTIMAL**; explored 9 of a search space of 9 candidate edit sets (0 explored = solver-based, no enumeration); optimality proved within the search space: True; remaining nogoods []; None
Objective: 1. hit every nogood (hard constraint; admitted profiles must exclude all violating profiles and be non-empty) 2. minimise number of edits 3. minimise permitted-behaviour (safe-profile) loss 4. minimise total wording length, then number of non-source-aligned edits
Tie-breaking: tuples compared lexicographically; first-found wins exact ties (deterministic candidate order). This is bounded exact enumeration, not MaxSAT.

## 10. Revised specification and re-verification
Revised SHA-256 `69695fbb26376293504244087379d441dc27649fdc07e69dae721d0924320df6`; re-verification status **VERIFIED_SAFE_WITHIN_SCOPE**.
- I-01 [clarify-event-order] line 1:8: original “After receiving the data message, the endpoint sends an acknowledgement and closes the session.” → proposed “The endpoint MUST complete the acknowledgement exchange before closing the session.” → final (re-read) “The endpoint MUST complete the acknowledgement exchange before closing the session.”
- I-02 [change-constraint-strength] line 2:8: original “The endpoint SHOULD retain the session until the peer's acknowledgement is received.” → proposed “The endpoint MUST retain the session until the peer's acknowledgement is received.” → final (re-read) “The endpoint MUST retain the session until the peer's acknowledgement is received.”
- round 1: status VERIFIED_SAFE_WITHIN_SCOPE; optimiser OPTIMAL; necessity [{'edit': 'I-01:ordered', 'nogoods_unsatisfied_without_it': ['NG-01', 'NG-03']}, {'edit': 'I-02:enforced', 'nogoods_unsatisfied_without_it': ['NG-02', 'NG-04']}]

**Property policy `rederive`** — held constant (original properties, never replaced): ['P1', 'P3']; added from the revised text: []; changed: []; no longer derivable from the revised text: []; not checked: []
### Coverage summary (revised)
- Instructions: 2 total, 2 linked to the model; unresolved: none
- Analysed by operator: ORDER-1: ['I-01'], MOD-1: ['I-02']
- Profiles checked: 1 of 1; limits reached: {'profile_enumeration': False, 'state_limit': False}

| Property | profiles safe | with violations | not fully checked |
|---|---|---|---|
| P1 | 1 | 0 | 0 |
| P3 | 1 | 0 | 0 |
Targeted violating profiles still possible after re-reading: 0; P_F(T') size 1, all verified safe: True

## 11. Behaviour preservation (latitude loss)
Universe: original specification's enumerated profile space under the same model.system assumptions (channels, bounds, state limit). Permitted before: profiles verified safe against all selected properties in the original specification; behaviours = event words of those profiles.
- Behaviour: a behaviour is an event word: the ordered sequence of (implementation, action) pairs of one run prefix. Observation rules: identical before and after: same event-word definition, same depth k, same word cap, same state limit, same model.system.
- Profile level (DEFINED): 0/1 = 0.0
- Trace level (DEFINED; depth k=10, word cap 20000, truncated=False): 0/257 = 0.0. Bounded-depth counts are NOT a comparison of every possible execution.
- Comparison status: **COMPLETE_WITHIN_DEPTH**. profile-level and trace-level losses are separate measures; trace-level counts depend on depth k and never cover all executions

## 12. Independent checker
Result: **CERTIFICATE_ACCEPTED** — {'verified': 94, 'rejected': 0, 'unverified': 0}. The checker shares only the reading-rule library (rule set 2.0.0) with the engine.

## 13. Conformance tests and execution status
generated = produced from the model; replayed_in_model = independently replayed by the checker; executed_against_implementation = only via an external run (none here).
| ID | Kind | Status | Property | Source instr. | Duplicate of | Target |
|---|---|---|---|---|---|---|
| CT-001 | normal_success_coverage | replayed_in_model | P1,P3 | ['I-01', 'I-02'] | None | covers transition t1 |
| CT-002 | normal_success_coverage | replayed_in_model | P1,P3 | ['I-01', 'I-02'] | None | covers transition t2 |
| CT-003 | normal_success_coverage | replayed_in_model | P1,P3 | ['I-01', 'I-02'] | None | covers transition t3 |
| CT-004 | normal_success_coverage | replayed_in_model | P1,P3 | ['I-01', 'I-02'] | None | covers transition t4 |
| CT-005 | normal_success_coverage | replayed_in_model | P1,P3 | ['I-01', 'I-02'] | None | covers transition t5 |
| CT-006 | counterexample | replayed_in_model | P1 | ['I-02'] | None | reproduces counterexample for P1 |
| CT-007 | clarification_regression | generated | P1 | ['I-02'] | None | clarification intended to remove the P1 violation |
| CT-008 | counterexample | replayed_in_model | P3 | ['I-02'] | None | reproduces counterexample for P3 |
| CT-009 | clarification_regression | generated | P3 | ['I-02'] | None | clarification intended to remove the P3 violation |
| CT-010 | counterexample | replayed_in_model | P1 | ['I-01'] | None | reproduces counterexample for P1 |
| CT-011 | clarification_regression | generated | P1 | ['I-01'] | None | clarification intended to remove the P1 violation |
| CT-012 | counterexample | replayed_in_model | P3 | ['I-01'] | CT-010 | reproduces counterexample for P3 |
| CT-013 | clarification_regression | generated | P3 | ['I-01'] | CT-011 | clarification intended to remove the P3 violation |
| CT-014 | counterexample | replayed_in_model | P1 | ['I-01'] | CT-010 | reproduces counterexample for P1 |
| CT-015 | clarification_regression | generated | P1 | ['I-01'] | CT-011 | clarification intended to remove the P1 violation |
| CT-016 | counterexample | replayed_in_model | P3 | ['I-01'] | CT-010 | reproduces counterexample for P3 |
| CT-017 | clarification_regression | generated | P3 | ['I-01'] | CT-011 | clarification intended to remove the P3 violation |
| CT-018 | counterexample | replayed_in_model | P1 | ['I-02'] | None | reproduces counterexample for P1 |
| CT-019 | clarification_regression | generated | P1 | ['I-02'] | None | clarification intended to remove the P1 violation |
| CT-020 | counterexample | replayed_in_model | P3 | ['I-02'] | None | reproduces counterexample for P3 |
| CT-021 | clarification_regression | generated | P3 | ['I-02'] | None | clarification intended to remove the P3 violation |
| CT-022 | counterexample | replayed_in_model | P1 | ['I-02'] | CT-018 | reproduces counterexample for P1 |
| CT-023 | clarification_regression | generated | P1 | ['I-02'] | CT-019 | clarification intended to remove the P1 violation |
| CT-024 | counterexample | replayed_in_model | P3 | ['I-02'] | None | reproduces counterexample for P3 |
| CT-025 | clarification_regression | generated | P3 | ['I-02'] | None | clarification intended to remove the P3 violation |
| CT-026 | counterexample | replayed_in_model | P1 | ['I-01'] | CT-010 | reproduces counterexample for P1 |
| CT-027 | clarification_regression | generated | P1 | ['I-01'] | CT-011 | clarification intended to remove the P1 violation |
| CT-028 | counterexample | replayed_in_model | P3 | ['I-01', 'I-02'] | None | reproduces counterexample for P3 |
| CT-029 | clarification_regression | generated | P3 | ['I-01', 'I-02'] | None | clarification intended to remove the P3 violation |
| CT-030 | counterexample | replayed_in_model | P1 | ['I-01'] | CT-010 | reproduces counterexample for P1 |
| CT-031 | clarification_regression | generated | P1 | ['I-01'] | CT-011 | clarification intended to remove the P1 violation |
| CT-032 | counterexample | replayed_in_model | P3 | ['I-01', 'I-02'] | CT-028 | reproduces counterexample for P3 |
| CT-033 | clarification_regression | generated | P3 | ['I-01', 'I-02'] | CT-029 | clarification intended to remove the P3 violation |
| CT-034 | counterexample | replayed_in_model | P1 | ['I-01'] | None | reproduces counterexample for P1 |
| CT-035 | clarification_regression | generated | P1 | ['I-01'] | None | clarification intended to remove the P1 violation |
| CT-036 | counterexample | replayed_in_model | P3 | ['I-01'] | CT-034 | reproduces counterexample for P3 |
| CT-037 | clarification_regression | generated | P3 | ['I-01'] | CT-035 | clarification intended to remove the P3 violation |
| CT-038 | counterexample | replayed_in_model | P1 | ['I-01'] | CT-034 | reproduces counterexample for P1 |
| CT-039 | clarification_regression | generated | P1 | ['I-01'] | CT-035 | clarification intended to remove the P1 violation |
| CT-040 | counterexample | replayed_in_model | P3 | ['I-01', 'I-02'] | None | reproduces counterexample for P3 |

## 14. Limitations
- Safe means safe within the stated model, bounds and coverage; UNANALYSED instructions are never treated as unambiguous.
- Instruction-to-FSM bindings are model-author supplied; operators are cue/regex based; the optimiser is exact bounded enumeration, not MaxSAT.
- No claim about real implementations; generated tests are not evidence that any implementation passed them.