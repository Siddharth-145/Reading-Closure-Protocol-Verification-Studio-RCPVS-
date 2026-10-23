# Results — RFC 1122 §4.2.2.13 case study (real source, author's abstraction, one real TCP stack)
Reproduce: `python case_studies/rfc1122_half_duplex_close/run_case_study.py` (artefacts in `outputs/`). Sources and caveats: `SOURCES.md`. Abstraction: `MODELLING.md`.
**This is a case study of the tool applied to a real specification sentence pair. It is not a finding about TCP, and nothing here says RFC 1122 is defective.**

## 1. What the tool did with the real sentences
| Step | Result |
|---|---|
| Instructions anchored | I-01 (MAY half-duplex close), I-02 (SHOULD send a reset when closing with data pending); author's paraphrase, spans and hashes recorded |
| Readings (MOD-1 modality rule; no errata link) | I-01: omitted / implemented. I-02: enforced / relaxed |
| Profiles | 4; 1 violating: **implemented + relaxed** (a host that closes with unread data but sends no reset) |
| Violated property | P1 (author-defined): the sender sees an orderly close although the receiver closed with unread data — silent data loss. P2 (can always finish) holds in all 4 profiles |
| Minimal combination / nogood | both readings together; neither alone violates |
| Coverage | both instructions analysed; no unanalysed instruction |

## 2. Clarification: where the objective and human judgment part ways
* **Scenario A (tool default):** the optimiser picks the shortest valid wording: *"A host MUST NOT implement a half-duplex close."* (1 edit, profile-level latitude loss 1/3, trace-level 3/9 at depth 10). A reviewer would probably reject this: it removes an option the RFC deliberately grants. This is exactly why audit mode exists and why the objective alone should not be trusted on real specifications.
* **Scenario B (author vetoes edits that remove the MAY option):** the tool selects **I-02 enforced** (SHOULD read as MUST). Same latitude loss (1/3). The revised property comparison adds the derived property for the new wording and reports it.
* In both scenarios the independent checker accepted the certificate and the SMT cross-check agreed on every comparable result (8/8 and 6/6; 6 results in each scenario are of property types SMT does not cover and are reported as unsupported).

## 3. Execution against a real implementation
System under test: the operating system's TCP stack via Python sockets on loopback (environment recorded in `outputs/summary.json`: Linux 6.18 VM, Python 3.12). Each executable test was run 5 times.
| Test | Meaning | Real stack result |
|---|---|---|
| Normal coverage (orderly path, scenarios A and B) | sender sends, receiver reads, closes; sender sees an orderly FIN | reproduced 5/5 |
| Normal coverage, scenario B (`r4`, `r5`) | receiver closes with data pending; a reset follows | reproduced 5/5: the sender's `recv()` raised a connection reset |
| Counterexample from the original spec | receiver closes with pending data, sender sees a FIN (silent loss) | **not** reproduced 0/5: the sender saw a reset instead; pass = the implementation does not exhibit the unsafe behaviour |
| Clarification regression | same sequence must be impossible after the edit | not reproduced 0/5 (pass) |
Interpretation: in this one scenario the tested stack behaves like the *enforced* reading. That is evidence about this stack in this sandbox only.

## 4. Limits (read before quoting any of this)
* The model covers one scenario and omits most of TCP; the properties P1/P2 are the author's formalisation of "to show that data was lost".
* The RFC text was read on a mirror and secondary sources; the authoritative copy and the full mailing-list message were not read by the tool or the assistant. RFC 2119 was not retrieved.
* The readings come from the generic modality rule, not from errata; the documented alternative scope reading (source 3) is only structurally encoded.
* One kernel, loopback, socket-API observations, no packet capture, no other operating systems.
* The SMT cross-check, checker and engine are all by one author; no human independent review has happened (`docs/REVIEW_PACKAGE.md`).
