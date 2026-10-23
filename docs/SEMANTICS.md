# Formal semantics used by RCPVS (for independent re-implementation and review)
This document is the reference a second implementer or reviewer should work from. If code and this document disagree, that is a finding.

## 1. Inputs
* **Specification**: lines; `[I-nn] text` anchors an instruction (untagged lines get `I-H` + first 6 hex of SHA-256 of the lowercased, whitespace-collapsed text). Lines starting with `#` and blank lines are ignored. Span = character offsets of the text after the tag; column is 1-based.
* **Model** (JSON): `roles` (name -> `{initial, states{name:{closed?}}, transitions[{id,src,dst,action}]}`), `system.implementations` (name -> `{role, peer?}`), `system.channel_capacity`, `system.assumptions` (`communication=asynchronous`, `channels=FIFO`, `message_loss=false`), `messages?`, `definitions`, `bindings` (instruction id -> `{role, ORDER|MODALITY|REF|DEF|SCOPE|TOL ...}`), `properties`.
* **Actions**: `!M` send M to the implementation's `peer`; `!M@X` send M to implementation X; `?M` (or `?M@X`, the suffix is a documentation annotation) receive M from the **head of the implementation's own mailbox**; anything else is an internal action.

## 2. Composition (asynchronous, bounded FIFO mailboxes)
Global state = (local state of every implementation, mailbox contents of every implementation). Mailbox = FIFO of message names, capacity `channel_capacity`.
One implementation moves per step (interleaving). A transition `t: s -a-> d` of implementation i is enabled iff i is in `s` and: for `!M[@X]` the target mailbox holds fewer than `capacity` messages; for `?M` i's mailbox is non-empty and its head is M; internal actions are always enabled. Effects: i moves to `d`; a send appends M to the target mailbox; a receive removes the head of i's mailbox. Mailboxes do not track the sender; no loss, duplication or reordering; mailboxes of different implementations are independent.
Consequence: results hold for these bounds only; they are not proofs for unbounded channels.

## 3. Readings and profiles
* Each instruction yields 0..n **readings** (ids, model patch). Reading 0 is the *baseline*. 0 readings = UNANALYSED (never "unambiguous"). 1 reading = fixed. >=2 readings = a **slot** `(implementation, instruction)` for every implementation whose role equals the binding role.
* A **profile** assigns one reading to every slot. Class: `mixed` iff some instruction is read differently by two implementations, else `common-mode`.
* **Patch operations** applied to a copy of the role FSM, each new transition tagged `instruction:reading`:
  `remove tid`; `bypass remove=tid action=a` (delete tid, add `src(tid) -a-> fresh closed-if-"close*" state`); `add t`; `rename_msg tid msg` (replace the message, keep the `@target`); `set_action tid action`; `set_closed states` (closed flag true exactly on the listed states).

## 4. Properties (violation = reachable witness; SAFE only if exploration completed)
`no_orphan_message`: a state where some implementation in a `closed` local state has a non-empty mailbox. `deadlock_freedom`: a state with no enabled transition that is not final (final = every implementation in a `final`/closed state, all mailboxes empty). `unspecified_reception`: a mailbox head that no local-reachable state of that implementation can ever receive. `invalid_transition`: a taken transition whose states or message are undeclared. `forbidden_action`: a taken transition with the given action (or id), optionally for one implementation. `state_invariant`: a state matching a forbidden conjunction of local states (optionally with empty mailboxes). `required_ordering`: `later` performed by an implementation that has not performed `earlier`. `can_complete`: a goal state is reachable. `always_can_complete`: from every reachable state a goal state is reachable. `inevitable_completion`: no reachable stuck state and no reachable cycle outside the goal. Goal = all implementations in goal states, all mailboxes empty.
Status: VIOLATION_FOUND (witness replays), VERIFIED_SAFE_WITHIN_SCOPE (exploration complete), INCOMPLETE_UNANALYSED (state/profile limit, or unanalysed instruction).

## 5. Derived notions
* **Minimal violating combination** of a violating profile: a set S of its non-baseline slot choices such that the profile with exactly S (other slots at baseline) violates and no proper subset does.
* **Conditional nogood**: a minimal partial assignment all of whose completions over the enumerated profile space violate a property.
* **Edit** (per instruction): keep one reading (text from a template/binding) or exclude one reading; it removes the other readings for every implementation. **Objective**: hit every nogood, then fewest edits, then fewest lost safe profiles, then shortest wording, then fewest non-source-aligned edits.
* **Latitude loss** `L = |V_before \ V_after| / |V_before|` over (a) safe profiles and (b) event words up to depth k; empty baseline = undefined.

## 6. What a certificate asserts and how it is checked
Source/revised spec hashes; instruction anchors; reading ids, rule versions, spans and patch digests; every (profile, property) status with a replayable trace; nogoods that cover all violating profiles; edit list that reproduces the revised text; removal of targeted profiles; property sets and comparison; replayable tests. The checker recomputes each item with `checker_rules.py` + its own explorer; a third path (`smt_check.py`, Z3 bounded model checking) cross-checks the safety/reachability properties.
