# Independent review package
**Status: NO independent human review has been performed.** This package exists so that someone other than the author can do it. Until a reviewer signs below, the strongest independence claim supported is: three verification paths written by one author, using different methods.

## Verification paths that exist
| Path | Method | Shared with the engine |
|---|---|---|
| Engine (`spec_analysis`, `fsm`, `engine`) | operator rules + explicit-state BFS | — |
| Checker (`checker_rules`, `certificate`) | separate rule code, separate explicit-state DFS, trace replay, hashes | documented conventions only (this document) |
| SMT (`smt_check`) | Z3 bounded model checking over the checker's derivation | documented semantics only; covers safety/reachability types, not liveness |

## What a reviewer should do (about a day)
1. Read `docs/SEMANTICS.md` and write an independent implementation of sections 2-4 (or review `smt_check.py` / `certificate.py` against them).
2. Run `python -m rcpvs.cli crosscheck --spec examples/<x>/spec.txt --model examples/<x>/model.json` for every example and for 3 models of your own; try to make the engine and a path disagree.
3. Inspect the shared assumptions listed below and decide whether each is reasonable.
4. Try the adversarial list in `tests/test_checker.py` and add cases.

## Assumptions all three paths share (a flaw here would NOT be caught)
* The composition semantics in section 2 (mailbox model, interleaving, capacity semantics).
* The meaning of the six patch operations (section 3) and that a reading is exactly its patch.
* The property definitions (section 4), especially "closed" and goal definitions supplied by the model author.
* The bindings and templates written by the model author (they define what text maps to what model change).
* Python's `re` semantics for cue patterns.

## Not covered by any second path
`always_can_complete`, `inevitable_completion`, `required_ordering` are evaluated by the engine and the checker's explicit evaluator only (not by SMT).

## Sign-off (blank)
| Reviewer | Affiliation | Date | Scope reviewed | Findings | Signature |
|---|---|---|---|---|---|
| | | | | | |
