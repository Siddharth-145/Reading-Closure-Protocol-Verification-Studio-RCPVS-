# Modelling decisions (author's abstraction — review before trusting results)
## Scope: one scenario only
A sender host S has sent one chunk of data to a receiver host R; the data has reached R's TCP but the application has not read it. R's application may then (a) read it and close normally, or (b) call CLOSE while the data is still pending. Everything else in TCP (retransmission, timers, windows, FIN-WAIT/TIME-WAIT, simultaneous close, data after CLOSE) is **out of the model**.

## Mapping from the RFC sentences to the model
| RFC idea | Model element | Decision |
|---|---|---|
| received data pending in TCP | receiver state R1 (`r1: ?DATA`) | pending = delivered to TCP, not yet read |
| application reads data | `r2: read` (R1 -> R2) then orderly `r3: !FIN` (R2 -> R5, closed) | orderly close after data is consumed |
| "A host MAY implement a half-duplex close" (I-01) | optional transition `r4: close` from R1 to R3 (CLOSE with data pending) | **implemented** reading adds `r4`; **omitted** reading has no such transition: the application must read before closing (data-preserving close) |
| "its TCP SHOULD send a reset" (I-02) | `r5: !RST` (R3 -> R4, closed) | **enforced** reading keeps the RST; **relaxed** reading renames it to `!FIN` (TCP closes normally, no reset) |
| "to show that data was lost" | sender S: `s2: ?RST` -> S2 (learns of loss); `s3: ?FIN` -> S3 (sees an orderly close) | S3 = sender believes the data was delivered |
| the purpose of the reset | P1 `state_invariant`: forbid **S in S3 while R in R4** | silent data loss: orderly close seen by the sender although the receiver closed with unread data |
| completion | P2 `always_can_complete`, goal S in {S2,S3}, R in {R4,R5} | both sides can always finish |

## Paraphrase constraints imposed by the tool
The reading rules treat words like "it", "that", "they" as possible unresolved references and mark the instruction UNANALYSED unless a REF binding exists. The paraphrase therefore avoids those words ("the data was lost" instead of "that data was lost"). This is a limitation of the tool, noted in the results.

## The alternative reading from source 3 (not modelled separately)
The reading "the SHOULD applies only to hosts that implement the half-duplex close" is structurally what the model encodes: the RST transition is reachable only through the optional `r4` path. The opposite scope ("RST for any close with unread data, even on a host that reads after close") is **not** modelled as a separate reading.

## Real-implementation mapping (see `tcp_harness.py`)
Sender `!DATA` = `send()`; receiver `?DATA` = data present in the receiver socket (checked with `MSG_PEEK`, not consumed); `read` = `recv()`; `close` = `close()`; the receiver's `!RST`/`!FIN` are kernel events observed *only* through the sender's next `recv()`: `ConnectionResetError` = RST, `b""` = FIN. Validity limits: loopback, one OS kernel, the socket API (not packet captures), several repetitions in one sandbox VM, no claim about other stacks.

## Not claimed
General TCP correctness; completeness of the model; that the author's abstraction matches the RFC authors' intent; anything about hosts other than the one tested.
