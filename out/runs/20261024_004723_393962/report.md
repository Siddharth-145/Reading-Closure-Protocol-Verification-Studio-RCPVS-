# Protocol Verification Report — Ping-Retry: MAY resend / MUST NOT close early (hypothetical)
_Reading-Closure Protocol Verification Studio. Engineered examples are illustrative, not evidence from real protocols._

## 1. Input specification
- Mode: **compile**; source SHA-256 `c6abbf5af9f6613bb0d00a262268956bf68ecedaa6619febdfbe858f7a00bff6`; rule set `2.0.0`
- Original status: **VIOLATION_FOUND**; final status: **VERIFIED_SAFE_WITHIN_SCOPE**

## 2. Model description and assumptions
- Communication: asynchronous, channels FIFO, message loss allowed: False, channel capacity 2
- Exploration bound: max_states 100000, max_profiles 5000. Results hold for these bounded FIFO channels only; they are NOT proofs for unbounded executions.
- Roles: client, server; implementations: C(client), S(server)
- Interpretation policy: {'MUST': 'enforced', 'SHOULD': 'both_readings', 'MAY': 'both_readings', 'MUST NOT': 'derived_safety_property'}

## 3. Reading operators and coverage
| Instruction | Line:Col | Rule | Status | Reason |
|---|---|---|---|---|
| I-01 | 2:8 | MOD-1 | ANALYSED | MAY: permitted optional path and no-optional-action path both represented |
| I-02 | 3:8 | MOD-1 | ANALYSED_SINGLE | MUST NOT: prohibition modelled as a safety property |

## 4. Alternative readings linked to source
| Instruction | Reading | Rule | Cue span | Affected | Preconditions |
|---|---|---|---|---|---|
| I-01 | omitted | MOD-1@2.0.0 | (11, 14) | [] | ['modality=MAY', 'policy=both_readings'] |
| I-01 | implemented | MOD-1@2.0.0 | (11, 14) | ['c_retx'] | ['modality=MAY', 'policy=both_readings'] |
| I-02 | prohibited | MOD-1@2.0.0 | (11, 19) | [] | ['modality=MUST NOT', 'policy=derived_safety_property'] |

## 5. Deployment profiles analysed
Checked 2 of 2 profiles (1 violating, 1 safe, 0 incomplete).

| Profile | Class | C::I-01 | Status |
|---|---|---|---|
| P1 | common-mode | implemented | VIOLATION_FOUND |
| P2 | common-mode | omitted | VERIFIED_SAFE_WITHIN_SCOPE |

## 6. Property results
### Coverage summary (original)
- Instructions: 2 total, 2 linked to the model; unresolved: none
- Analysed by operator: MOD-1: ['I-01', 'I-02']
- Profiles checked: 2 of 2; limits reached: {'profile_enumeration': False, 'state_limit': False}

| Property | profiles safe | with violations | not fully checked |
|---|---|---|---|
| P1 | 1 | 1 | 0 |
| P2 | 1 | 1 | 0 |
| PROH-I-02 | 2 | 0 | 0 |

## 7. Counterexamples and causes
**P1** (message pending for a closed endpoint) violated by common-mode profile `{'C::I-01': 'implemented'}`.
Minimal violating combinations (no proper subset of a listed combination, with all other slots at baseline, reproduces this violation; exhaustive=True, this profile itself minimal=True): [[{'impl': 'C', 'instruction': 'I-01', 'reading': 'implemented'}]]

- I-01 (line 2, col 8): “The client MAY retransmit the ping.” → reading `implemented` (optional behaviour implemented); affected ['c_retx']; rule MOD-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)
- I-01 (line 2, col 8): “The client MAY retransmit the ping.” → reading `implemented` (optional behaviour implemented); affected ['c_retx']; rule MOD-1@2.0.0; transition tagged I-01:implemented occurs in the counterexample trace

| Step | Impl | Action | Transition | Reading tag | state C | state S |
|---|---|---|---|---|---|---|
| 1 | C | `!PING` | c1 | base | C1 | S0 |
| 2 | C | `!PING` | c_retx | I-01:implemented | C1 | S0 |
| 3 | S | `?PING` | s1 | base | C1 | S1 |
| 4 | S | `!PONG` | s2 | base | C1 | S2 |
| 5 | S | `close` | s3 | base | C1 | S3 |

**P2** (state from which the completion goal is unreachable (deadlock/livelock/bad closure)) violated by common-mode profile `{'C::I-01': 'implemented'}`.
Minimal violating combinations (no proper subset of a listed combination, with all other slots at baseline, reproduces this violation; exhaustive=True, this profile itself minimal=True): [[{'impl': 'C', 'instruction': 'I-01', 'reading': 'implemented'}]]

- I-01 (line 2, col 8): “The client MAY retransmit the ping.” → reading `implemented` (optional behaviour implemented); affected ['c_retx']; rule MOD-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)
- I-01 (line 2, col 8): “The client MAY retransmit the ping.” → reading `implemented` (optional behaviour implemented); affected ['c_retx']; rule MOD-1@2.0.0; transition tagged I-01:implemented occurs in the counterexample trace

| Step | Impl | Action | Transition | Reading tag | state C | state S |
|---|---|---|---|---|---|---|
| 1 | C | `!PING` | c1 | base | C1 | S0 |
| 2 | C | `!PING` | c_retx | I-01:implemented | C1 | S0 |
| 3 | S | `?PING` | s1 | base | C1 | S1 |
| 4 | C | `!PING` | c_retx | I-01:implemented | C1 | S1 |
| 5 | S | `!PONG` | s2 | base | C1 | S2 |
| 6 | C | `?PONG` | c2 | base | C2 | S2 |
| 7 | C | `close` | c3 | base | C3 | S2 |
| 8 | S | `close` | s3 | base | C3 | S3 |

## 8. Conditional nogoods (selected irredundant cover)
- NG-01: forbid [('C', 'I-01', 'implemented')] (instructions ['I-01']; properties ['P1', 'P2']; assumptions `5db64869172a328b`). Irredundancy witness: `{'C::I-01': 'implemented'}`. Meaning: these readings must not remain simultaneously possible.

## 9. Candidate clarifications and optimisation objective
Objective (lexicographic): hit every nogood > fewest edits > least latitude loss > shortest, source-aligned wording.
Candidates: [('I-01', 'change-constraint-strength', 'omitted'), ('I-01', 'change-constraint-strength', 'implemented')]
Optimiser: **OPTIMAL**; explored 3 of a search space of 3 candidate edit sets (0 explored = solver-based, no enumeration); optimality proved within the search space: True; remaining nogoods []; None
Objective: 1. hit every nogood (hard constraint; admitted profiles must exclude all violating profiles and be non-empty) 2. minimise number of edits 3. minimise permitted-behaviour (safe-profile) loss 4. minimise total wording length, then number of non-source-aligned edits
Tie-breaking: tuples compared lexicographically; first-found wins exact ties (deterministic candidate order). This is bounded exact enumeration, not MaxSAT.

## 10. Revised specification and re-verification
Revised SHA-256 `99642ffdb3640a3cdbe7a91782386e38eef6e2f0af2a5a92cb214f673c0d7cc8`; re-verification status **VERIFIED_SAFE_WITHIN_SCOPE**.
- I-01 [change-constraint-strength] line 2:8: original “The client MAY retransmit the ping.” → proposed “The client MUST NOT retransmit the ping.” → final (re-read) “The client MUST NOT retransmit the ping.”
- round 1: status VERIFIED_SAFE_WITHIN_SCOPE; optimiser OPTIMAL; necessity [{'edit': 'I-01:omitted', 'nogoods_unsatisfied_without_it': ['NG-01']}]

**Property policy `rederive`** — held constant (original properties, never replaced): ['P1', 'P2', 'PROH-I-02']; added from the revised text: ['PROH-I-01']; changed: []; no longer derivable from the revised text: []; not checked: []
- new property `PROH-I-01` (forbidden_action) from I-01 span [78, 118] modality MUST NOT, revision `99642ffdb364…`: results ['VERIFIED_SAFE_WITHIN_SCOPE']
### Coverage summary (revised)
- Instructions: 2 total, 2 linked to the model; unresolved: none
- Analysed by operator: MOD-1: ['I-01', 'I-02']
- Profiles checked: 1 of 1; limits reached: {'profile_enumeration': False, 'state_limit': False}

| Property | profiles safe | with violations | not fully checked |
|---|---|---|---|
| P1 | 1 | 0 | 0 |
| P2 | 1 | 0 | 0 |
| PROH-I-02 | 1 | 0 | 0 |
| PROH-I-01 | 1 | 0 | 0 |
Targeted violating profiles still possible after re-reading: 0; P_F(T') size 1, all verified safe: True

## 11. Behaviour preservation (latitude loss)
Universe: original specification's enumerated profile space under the same model.system assumptions (channels, bounds, state limit). Permitted before: profiles verified safe against all selected properties in the original specification; behaviours = event words of those profiles.
- Behaviour: a behaviour is an event word: the ordered sequence of (implementation, action) pairs of one run prefix. Observation rules: identical before and after: same event-word definition, same depth k, same word cap, same state limit, same model.system.
- Profile level (DEFINED): 0/1 = 0.0
- Trace level (DEFINED; depth k=10, word cap 20000, truncated=False): 0/12 = 0.0. Bounded-depth counts are NOT a comparison of every possible execution.
- Comparison status: **COMPLETE_WITHIN_DEPTH**. profile-level and trace-level losses are separate measures; trace-level counts depend on depth k and never cover all executions

## 12. Independent checker
Result: **CERTIFICATE_ACCEPTED** — {'verified': 42, 'rejected': 0, 'unverified': 0}. The checker shares only the reading-rule library (rule set 2.0.0) with the engine.

## 13. Conformance tests and execution status
generated = produced from the model; replayed_in_model = independently replayed by the checker; executed_against_implementation = only via an external run (none here).
| ID | Kind | Status | Property | Source instr. | Duplicate of | Target |
|---|---|---|---|---|---|---|
| CT-001 | normal_success_coverage | replayed_in_model | P1,P2,PROH-I-01,PROH-I-02 | ['I-01', 'I-02'] | None | covers transition c1 |
| CT-002 | normal_success_coverage | replayed_in_model | P1,P2,PROH-I-01,PROH-I-02 | ['I-01', 'I-02'] | None | covers transition c2 |
| CT-003 | normal_success_coverage | replayed_in_model | P1,P2,PROH-I-01,PROH-I-02 | ['I-01', 'I-02'] | None | covers transition c3 |
| CT-004 | counterexample | replayed_in_model | P1 | ['I-01'] | None | reproduces counterexample for P1 |
| CT-005 | clarification_regression | generated | P1 | ['I-01'] | None | clarification intended to remove the P1 violation |
| CT-006 | counterexample | replayed_in_model | P2 | ['I-01'] | None | reproduces counterexample for P2 |
| CT-007 | clarification_regression | generated | P2 | ['I-01'] | None | clarification intended to remove the P2 violation |

## 14. Limitations
- Safe means safe within the stated model, bounds and coverage; UNANALYSED instructions are never treated as unambiguous.
- Instruction-to-FSM bindings are model-author supplied; operators are cue/regex based; the optimiser is exact bounded enumeration, not MaxSAT.
- No claim about real implementations; generated tests are not evidence that any implementation passed them.