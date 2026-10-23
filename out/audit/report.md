# Protocol Verification Report — Ack-Close demo (hypothetical)
_Reading-Closure Protocol Verification Studio. Engineered examples are illustrative, not evidence from real protocols._

## 1. Input specification
- Mode: **audit**; source SHA-256 `b2064c70c798a17d54bc296e3d542780f47a036ed6bc95b86ac4f7882e73a542`; rule set `2.0.0`
- Original status: **VIOLATION_FOUND**; final status: **VIOLATION_FOUND**

## 2. Model description and assumptions
- Communication: asynchronous, channels FIFO, message loss allowed: False, channel capacity 2
- Exploration bound: max_states 100000, max_profiles 5000. Results hold for these bounded FIFO channels only; they are NOT proofs for unbounded executions.
- Roles: endpoint; implementations: A(endpoint), B(endpoint)
- Interpretation policy: {'MUST': 'enforced', 'SHOULD': 'both_readings', 'MAY': 'both_readings', 'MUST NOT': 'derived_safety_property'}

## 3. Reading operators and coverage
| Instruction | Line:Col | Rule | Status | Reason |
|---|---|---|---|---|
| I-01 | 2:8 | ORDER-1 | ANALYSED | conjunction of two events without ordering cue |
| I-02 | 3:8 | MOD-1 | ANALYSED | SHOULD admits enforced and relaxed readings |

## 4. Alternative readings linked to source
| Instruction | Reading | Rule | Cue span | Affected | Preconditions |
|---|---|---|---|---|---|
| I-01 | ordered | ORDER-1@2.0.0 | (47, 82) | [] | ['conjunction without ordering cue', 'binding gives both events'] |
| I-01 | unordered | ORDER-1@2.0.0 | (47, 82) | ['t3'] | ['conjunction without ordering cue', 'binding gives both events'] |
| I-02 | enforced | MOD-1@2.0.0 | (13, 19) | [] | ['modality=SHOULD', 'policy=both_readings'] |
| I-02 | relaxed | MOD-1@2.0.0 | (13, 19) | ['t4'] | ['modality=SHOULD', 'policy=both_readings'] |

## 5. Deployment profiles analysed
Checked 16 of 16 profiles (11 violating, 5 safe, 0 incomplete).

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
| P11 | common-mode | unordered | enforced | unordered | enforced | VERIFIED_SAFE_WITHIN_SCOPE |
| P12 | mixed | unordered | enforced | unordered | relaxed | VERIFIED_SAFE_WITHIN_SCOPE |
| P13 | mixed | unordered | relaxed | ordered | enforced | VIOLATION_FOUND |
| P14 | mixed | unordered | relaxed | ordered | relaxed | VIOLATION_FOUND |
| P15 | mixed | unordered | relaxed | unordered | enforced | VERIFIED_SAFE_WITHIN_SCOPE |
| P16 | common-mode | unordered | relaxed | unordered | relaxed | VERIFIED_SAFE_WITHIN_SCOPE |

## 6. Property results
### Coverage summary (original)
- Instructions: 2 total, 2 linked to the model; unresolved: none
- Analysed by operator: ORDER-1: ['I-01'], MOD-1: ['I-02']
- Profiles checked: 16 of 16; limits reached: {'profile_enumeration': False, 'state_limit': False}

| Property | profiles safe | with violations | not fully checked |
|---|---|---|---|
| P1 | 5 | 11 | 0 |
| P2 | 5 | 11 | 0 |

## 7. Counterexamples and causes
**P1** (message pending for a closed endpoint) violated by mixed profile `{'A::I-01': 'ordered', 'A::I-02': 'enforced', 'B::I-01': 'ordered', 'B::I-02': 'relaxed'}`.
Minimal violating combinations (no proper subset of a listed combination, with all other slots at baseline, reproduces this violation; exhaustive=True, this profile itself minimal=True): [[{'impl': 'B', 'instruction': 'I-02', 'reading': 'relaxed'}]]

- I-02 (line 3, col 8): “The endpoint SHOULD retain the session until the peer's acknowledgement is received.” → reading `relaxed` (treated as optional / bypassable); affected ['t4']; rule MOD-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)
- I-02 (line 3, col 8): “The endpoint SHOULD retain the session until the peer's acknowledgement is received.” → reading `relaxed` (treated as optional / bypassable); affected ['t4']; rule MOD-1@2.0.0; transition tagged I-02:relaxed occurs in the counterexample trace

| Step | Impl | Action | Transition | Reading tag | state A | state B |
|---|---|---|---|---|---|---|
| 1 | A | `!DATA` | t1 | base | E1 | E0 |
| 2 | B | `!DATA` | t1 | base | E1 | E1 |
| 3 | A | `?DATA` | t2 | base | E2 | E1 |
| 4 | A | `!ACK` | t3 | base | E3 | E1 |
| 5 | B | `?DATA` | t2 | base | E3 | E2 |
| 6 | B | `!ACK` | t3 | base | E3 | E3 |
| 7 | B | `close` | t4'~I-02:relaxed | I-02:relaxed | E3 | CLOSE~I-02:relaxed |

**P2** (state from which the completion goal is unreachable (deadlock/livelock/bad closure)) violated by mixed profile `{'A::I-01': 'ordered', 'A::I-02': 'enforced', 'B::I-01': 'ordered', 'B::I-02': 'relaxed'}`.
Minimal violating combinations (no proper subset of a listed combination, with all other slots at baseline, reproduces this violation; exhaustive=True, this profile itself minimal=True): [[{'impl': 'B', 'instruction': 'I-02', 'reading': 'relaxed'}]]

- I-02 (line 3, col 8): “The endpoint SHOULD retain the session until the peer's acknowledgement is received.” → reading `relaxed` (treated as optional / bypassable); affected ['t4']; rule MOD-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)
- I-02 (line 3, col 8): “The endpoint SHOULD retain the session until the peer's acknowledgement is received.” → reading `relaxed` (treated as optional / bypassable); affected ['t4']; rule MOD-1@2.0.0; transition tagged I-02:relaxed occurs in the counterexample trace

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

- I-01 (line 2, col 8): “After receiving the data message, the endpoint sends an acknowledgement and closes the session.” → reading `unordered` (second event may occur instead of completing the first); affected ['t3']; rule ORDER-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)
- I-01 (line 2, col 8): “After receiving the data message, the endpoint sends an acknowledgement and closes the session.” → reading `unordered` (second event may occur instead of completing the first); affected ['t3']; rule ORDER-1@2.0.0; transition tagged I-01:unordered occurs in the counterexample trace

| Step | Impl | Action | Transition | Reading tag | state A | state B |
|---|---|---|---|---|---|---|
| 1 | A | `!DATA` | t1 | base | E1 | E0 |
| 2 | B | `!DATA` | t1 | base | E1 | E1 |
| 3 | A | `?DATA` | t2 | base | E2 | E1 |
| 4 | A | `!ACK` | t3 | base | E3 | E1 |
| 5 | B | `?DATA` | t2 | base | E3 | E2 |
| 6 | B | `close` | t3'~I-01:unordered | I-01:unordered | E3 | CLOSE~I-01:unordered |

**P2** (state from which the completion goal is unreachable (deadlock/livelock/bad closure)) violated by mixed profile `{'A::I-01': 'ordered', 'A::I-02': 'enforced', 'B::I-01': 'unordered', 'B::I-02': 'enforced'}`.
Minimal violating combinations (no proper subset of a listed combination, with all other slots at baseline, reproduces this violation; exhaustive=True, this profile itself minimal=True): [[{'impl': 'B', 'instruction': 'I-01', 'reading': 'unordered'}]]

- I-01 (line 2, col 8): “After receiving the data message, the endpoint sends an acknowledgement and closes the session.” → reading `unordered` (second event may occur instead of completing the first); affected ['t3']; rule ORDER-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)
- I-01 (line 2, col 8): “After receiving the data message, the endpoint sends an acknowledgement and closes the session.” → reading `unordered` (second event may occur instead of completing the first); affected ['t3']; rule ORDER-1@2.0.0; transition tagged I-01:unordered occurs in the counterexample trace

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

- I-01 (line 2, col 8): “After receiving the data message, the endpoint sends an acknowledgement and closes the session.” → reading `unordered` (second event may occur instead of completing the first); affected ['t3']; rule ORDER-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)
- I-01 (line 2, col 8): “After receiving the data message, the endpoint sends an acknowledgement and closes the session.” → reading `unordered` (second event may occur instead of completing the first); affected ['t3']; rule ORDER-1@2.0.0; transition tagged I-01:unordered occurs in the counterexample trace
- I-02 (line 3, col 8): “The endpoint SHOULD retain the session until the peer's acknowledgement is received.” → reading `relaxed` (treated as optional / bypassable); affected ['t4']; rule MOD-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)

| Step | Impl | Action | Transition | Reading tag | state A | state B |
|---|---|---|---|---|---|---|
| 1 | A | `!DATA` | t1 | base | E1 | E0 |
| 2 | B | `!DATA` | t1 | base | E1 | E1 |
| 3 | A | `?DATA` | t2 | base | E2 | E1 |
| 4 | A | `!ACK` | t3 | base | E3 | E1 |
| 5 | B | `?DATA` | t2 | base | E3 | E2 |
| 6 | B | `close` | t3'~I-01:unordered | I-01:unordered | E3 | CLOSE~I-01:unordered |

**P2** (state from which the completion goal is unreachable (deadlock/livelock/bad closure)) violated by mixed profile `{'A::I-01': 'ordered', 'A::I-02': 'enforced', 'B::I-01': 'unordered', 'B::I-02': 'relaxed'}`.
Minimal violating combinations (no proper subset of a listed combination, with all other slots at baseline, reproduces this violation; exhaustive=True, this profile itself minimal=False): [[{'impl': 'B', 'instruction': 'I-01', 'reading': 'unordered'}], [{'impl': 'B', 'instruction': 'I-02', 'reading': 'relaxed'}]]

- I-01 (line 2, col 8): “After receiving the data message, the endpoint sends an acknowledgement and closes the session.” → reading `unordered` (second event may occur instead of completing the first); affected ['t3']; rule ORDER-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)
- I-01 (line 2, col 8): “After receiving the data message, the endpoint sends an acknowledgement and closes the session.” → reading `unordered` (second event may occur instead of completing the first); affected ['t3']; rule ORDER-1@2.0.0; transition tagged I-01:unordered occurs in the counterexample trace
- I-02 (line 3, col 8): “The endpoint SHOULD retain the session until the peer's acknowledgement is received.” → reading `relaxed` (treated as optional / bypassable); affected ['t4']; rule MOD-1@2.0.0; member of a minimal violating combination (changing it back removes the violation)

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
- NG-01: forbid [('A', 'I-01', 'ordered'), ('A', 'I-02', 'relaxed')] (instructions ['I-01', 'I-02']; properties ['P1', 'P2']; assumptions `14d1f9fe37285d5b`). Irredundancy witness: `{'A::I-01': 'ordered', 'A::I-02': 'relaxed', 'B::I-01': 'ordered', 'B::I-02': 'enforced'}`. Meaning: these readings must not remain simultaneously possible.
- NG-03: forbid [('A', 'I-01', 'unordered'), ('B', 'I-01', 'ordered')] (instructions ['I-01']; properties ['P1', 'P2']; assumptions `14d1f9fe37285d5b`). Irredundancy witness: `{'A::I-01': 'unordered', 'A::I-02': 'enforced', 'B::I-01': 'ordered', 'B::I-02': 'relaxed'}`. Meaning: these readings must not remain simultaneously possible.
- NG-02: forbid [('A', 'I-01', 'ordered'), ('B', 'I-01', 'unordered')] (instructions ['I-01']; properties ['P1', 'P2']; assumptions `14d1f9fe37285d5b`). Irredundancy witness: `{'A::I-01': 'ordered', 'A::I-02': 'enforced', 'B::I-01': 'unordered', 'B::I-02': 'enforced'}`. Meaning: these readings must not remain simultaneously possible.
- NG-04: forbid [('A', 'I-01', 'ordered'), ('B', 'I-02', 'relaxed')] (instructions ['I-01', 'I-02']; properties ['P1', 'P2']; assumptions `14d1f9fe37285d5b`). Irredundancy witness: `{'A::I-01': 'ordered', 'A::I-02': 'enforced', 'B::I-01': 'ordered', 'B::I-02': 'relaxed'}`. Meaning: these readings must not remain simultaneously possible.

## 9. Candidate clarifications and optimisation objective
Objective (lexicographic): hit every nogood > fewest edits > least latitude loss > shortest, source-aligned wording.
Candidates: [('I-01', 'clarify-event-order', 'ordered'), ('I-01', 'clarify-event-order', 'unordered'), ('I-02', 'change-constraint-strength', 'enforced'), ('I-02', 'change-constraint-strength', 'relaxed')]
Optimiser: **OPTIMAL**; explored 9 of a search space of 9 candidate edit sets (0 explored = solver-based, no enumeration); optimality proved within the search space: True; remaining nogoods []; None
Objective: 1. hit every nogood (hard constraint; admitted profiles must exclude all violating profiles and be non-empty) 2. minimise number of edits 3. minimise permitted-behaviour (safe-profile) loss 4. minimise total wording length, then number of non-source-aligned edits
Tie-breaking: tuples compared lexicographically; first-found wins exact ties (deterministic candidate order). This is bounded exact enumeration, not MaxSAT.

### Recommended clarifications (audit mode — for human review; nothing was changed)
- **I-01** [clarify-event-order]: “After receiving the data message, the endpoint sends an acknowledgement and closes the session.” → “The endpoint MAY close the session before the acknowledgement exchange is completed.”
- necessity: {'edit': 'I-01:unordered', 'nogoods_unsatisfied_without_it': ['NG-01', 'NG-02', 'NG-03', 'NG-04', 'NG-05', 'NG-06']}

## 14. Limitations
- Safe means safe within the stated model, bounds and coverage; UNANALYSED instructions are never treated as unambiguous.
- Instruction-to-FSM bindings are model-author supplied; operators are cue/regex based; the optimiser is exact bounded enumeration, not MaxSAT.
- No claim about real implementations; generated tests are not evidence that any implementation passed them.