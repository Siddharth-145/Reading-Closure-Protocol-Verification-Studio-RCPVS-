# Sources (traceable documents) — RFC 1122 §4.2.2.13 case study
Retrieval date: 2026-10-17, via the assistant's web-search tool. **Everything below should be re-verified by a human against the authoritative copy.**

| # | Document | Used for | Access note |
|---|---|---|---|
| 1 | R. Braden (Ed.), *Requirements for Internet Hosts — Communication Layers*, RFC 1122, October 1989, **section 4.2.2.13 "Closing a Connection"** (cross-references RFC 793 section 3.5) | the normative sentences about a half-duplex TCP close: a host MAY implement it; if such a host closes while received data is still pending (or data arrives after CLOSE) its TCP SHOULD send a reset to show data was lost | text read on a mirror, https://www.freesoft.org/CIE/RFC/1122/99.htm . The authoritative RFC Editor copy was **not** retrieved in this session. |
| 2 | linux-netdev mailing-list thread "TCP - RST flag", message by Eric Dumazet, 2011-08-23, https://lists.openwall.net/netdev/2011/08/23/93 | shows a kernel developer applying the same sentence: data ACKed before close() but not yet read by the application means TCP must send an RST | secondary source quoting item 1 |
| 3 | PostgreSQL mailing-list message by Tom Lane (2000), https://www.postgresql.org/message-id/27958.962732804@sss.pgh.pa.us | a documented *alternative reading*: the SHOULD-send-RST requirement pertains only to hosts that implement the half-duplex close sequence, not to every close of a socket | only fragments of the message were visible to the assistant; a reviewer must read the full message before relying on it |
| 4 | RFC 2119 (meaning of MAY / SHOULD) | the general rule that SHOULD admits valid reasons to deviate, which is why the *relaxed* reading of SHOULD is modelled | **not retrieved** in this session; cited from general knowledge — verify |

## What is and is not claimed
* The tool's input is the author's **paraphrase** (`spec.txt`), not the RFC text, so that no RFC wording is reproduced and so that the tool's cue patterns apply. Paraphrase choices are listed in `MODELLING.md`; a reviewer should confirm each against item 1.
* **No errata link is recorded.** The alternative readings come from the *modality* rule (MAY / SHOULD) and are consistent with the documented disagreement in item 3; they are **not** errata-derived, and the tool records "(no errata link supplied)".
* Nothing here says RFC 1122 is defective. SHOULD is deliberately weaker than MUST; the case study shows what the tool reports when the *relaxed* reading is allowed.
