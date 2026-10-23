"""Generates the engineered example protocols (deterministic). Run: python examples/build_examples.py
These are designed test cases for the mechanisms, NOT evidence from real protocols."""
import json, os, shutil
D = os.path.dirname(os.path.abspath(__file__))
ASSUME = {"communication": "asynchronous", "channels": "FIFO", "message_loss": False}


def w(name, spec, model, expected, readme):
    d = f"{D}/{name}"; os.makedirs(d, exist_ok=True)
    open(f"{d}/spec.txt", "w").write(spec)
    json.dump(model, open(f"{d}/model.json", "w"), indent=1)
    json.dump(dict(expected, synthetic=True, note="Synthetic engineered fixture; not real-world validation"), open(f"{d}/expected.json", "w"), indent=1)
    open(f"{d}/README.md", "w").write(readme + "\n_Synthetic fixture: an engineered test case for the mechanism above, not evidence from real protocols._\n")


def role(init, states, trans, closed=()):
    return {"initial": init, "states": {s: ({"closed": True} if s in closed else {}) for s in states},
            "transitions": [{"id": i, "src": a, "dst": b, "action": c} for i, a, b, c in trans]}


def sysm(a, ra, b, rb, cap): return {"implementations": {a: {"role": ra, "peer": b}, b: {"role": rb, "peer": a}}, "channel_capacity": cap, "assumptions": dict(ASSUME)}


def prop(i, kind, typ, desc, **kw): return dict({"id": i, "kind": kind, "type": typ, "description": desc, "scope": "bounded FIFO channels", "assumptions": {}, "bounds": {}}, **kw)


# ---- REF -----------------------------------------------------------------------------------
w("ref_ambiguity", "[I-01] The server acknowledges it.\n", {
    "name": "REF ambiguity (hypothetical)", "default_properties": ["P1", "P2"], "messages": ["REQ", "PING", "ACKREQ", "ACKPING"],
    "roles": {"client": role("C0", ["C0", "C1", "C2", "C3"], [("c1", "C0", "C1", "!REQ"), ("c2", "C1", "C2", "!PING"), ("c3", "C2", "C3", "?ACKREQ")], ["C3"]),
              "server": role("S0", ["S0", "S1", "S2", "S3"], [("s1", "S0", "S1", "?REQ"), ("s2", "S1", "S2", "?PING"), ("s3", "S2", "S3", "!ACKREQ")], ["S3"])},
    "system": sysm("C", "client", "S", "server", 2), "definitions": {}, "errata": {},
    "bindings": {"I-01": {"role": "server", "REF": {"phrase": "it", "transition": "s3", "candidates": [
        {"id": "request", "msg": "ACKREQ", "cue": r"\bthe request\b", "text": "The server MUST acknowledge the request."},
        {"id": "ping", "msg": "ACKPING", "cue": r"\bthe ping\b", "text": "The server MUST acknowledge the ping."}]}}},
    "properties": [prop("P1", "safety", "unspecified_reception", "No message at a channel head can never be consumed."),
                   prop("P2", "functionality", "always_can_complete", "Both sides can always reach their closed states.", goal={"C": ["C3"], "S": ["S3"]})]},
  {"runs": [{"expect": {"original_status": "VIOLATION_FOUND", "final_status": "VERIFIED_SAFE_WITHIN_SCOPE", "edits": [["I-01", "request"]], "checker_accepted": True}}]},
  "# ref_ambiguity\nThe pronoun 'it' may denote the request or the ping. Reading `ping` makes the server send an acknowledgement the client cannot receive (unspecified reception). Tests REF (positive), explicit-referent cue (negative) and disambiguation edit.\n")

# ---- SCOPE ---------------------------------------------------------------------------------
w("scope_ambiguity", "[I-01] The server MUST NOT reply to a repeated request in the session.\n", {
    "name": "SCOPE ambiguity (hypothetical)", "default_properties": ["P1", "P2"], "messages": ["REQ", "OK"],
    "roles": {"client": role("C0", ["C0", "C1", "C2", "C3", "C4", "C5"], [("c1", "C0", "C1", "!REQ"), ("c2", "C1", "C2", "!REQ"), ("c3", "C2", "C3", "!REQ"), ("c4", "C3", "C4", "?OK"), ("c5", "C4", "C5", "close")], ["C5"]),
              "server": role("S0", ["S0", "S1", "S2", "S3", "S4", "S5", "S6"], [("s1", "S0", "S1", "?REQ"), ("s2", "S1", "S2", "!OK"), ("s3", "S2", "S3", "?REQ"), ("s4", "S3", "S4", "!OK"), ("s5", "S4", "S5", "?REQ"), ("s6", "S5", "S6", "!OK")], ["S6"])},
    "system": sysm("C", "client", "S", "server", 3), "definitions": {}, "errata": {},
    "bindings": {"I-01": {"role": "server", "SCOPE": {"trigger": r"\brepeated request\b", "scopes": [
        {"id": "narrow", "silence": ["s4"], "cue": r"immediately repeated", "text": "The server MUST NOT reply to an immediately repeated request."},
        {"id": "broad", "silence": ["s4", "s6"], "cue": r"any repeated request", "text": "The server MUST NOT reply to any repeated request in the session."}]}}},
    "properties": [prop("P1", "safety", "no_orphan_message", "No message is pending for a closed endpoint."),
                   prop("P2", "functionality", "always_can_complete", "Both sides can always close with empty channels.", goal={"C": ["C5"], "S": ["S6"]})]},
  {"runs": [{"expect": {"original_status": "VIOLATION_FOUND", "final_status": "VERIFIED_SAFE_WITHIN_SCOPE", "edits": [["I-01", "broad"]], "checker_accepted": True,
                        "profile_status": {"narrow": "VIOLATION_FOUND", "broad": "VERIFIED_SAFE_WITHIN_SCOPE"}}}]},
  "# scope_ambiguity\nNarrow scope silences only the reply to the 2nd request; broad scope silences replies to the 2nd and 3rd. The narrow reading leaves a stray OK for a closed client; the broad reading is safe. Narrow and broad give different verification results.\n")

# ---- DEF -----------------------------------------------------------------------------------
w("definition_ambiguity", "[I-01] The server MUST ignore messages once the session is closed.\n", {
    "name": "DEF ambiguity (hypothetical)", "default_properties": ["P1", "P2"], "messages": ["REQ", "RESP", "CLOSE"],
    "roles": {"client": role("C0", ["C0", "C1", "C2", "C3"], [("c1", "C0", "C1", "!REQ"), ("c2", "C1", "C2", "?RESP"), ("c3", "C2", "C3", "!CLOSE")], ["C3"]),
              "server": role("S0", ["S0", "S1", "S2", "S3"], [("s1", "S0", "S1", "?REQ"), ("s2", "S1", "S2", "!RESP"), ("s3", "S2", "S3", "?CLOSE")], ["S3"])},
    "system": sysm("C", "client", "S", "server", 2), "errata": {},
    "definitions": {"closed": {"source": "§2.1 (hypothetical)", "senses": [
        {"id": "strict", "states": ["S3"], "cue": r"fully closed", "text": "The server MUST ignore messages once the session is fully closed."},
        {"id": "half", "states": ["S2", "S3"], "cue": r"half-closed", "text": "The server MUST ignore messages once the session is half-closed."}]}},
    "bindings": {"I-01": {"role": "server", "DEF": {"term": "closed"}}},
    "properties": [prop("P1", "safety", "no_orphan_message", "No message is pending for a closed endpoint."),
                   prop("P2", "functionality", "always_can_complete", "Both sides can always close.", goal={"C": ["C3"], "S": ["S3"]})]},
  {"runs": [{"expect": {"original_status": "VIOLATION_FOUND", "final_status": "VERIFIED_SAFE_WITHIN_SCOPE", "edits": [["I-01", "strict"]], "checker_accepted": True}}]},
  "# definition_ambiguity\n'closed' may mean fully closed (S3) or half-closed (S2 or S3). Under the half-closed sense the CLOSE message is pending at an endpoint already considered closed.\n")

# ---- TOL -----------------------------------------------------------------------------------
w("tolerance_boundary", "[I-01] The client MUST accept a reply received within 5 seconds of the request.\n", {
    "name": "TOL boundary (hypothetical)", "default_properties": ["P1", "P2"], "messages": ["REQ", "REPLY", "REPLYLIMIT"],
    "roles": {"client": role("C0", ["C0", "C1", "C2", "C3"], [("c1", "C0", "C1", "!REQ"), ("c2", "C1", "C2", "?REPLY"), ("c3", "C1", "C3", "?REPLYLIMIT")], ["C2", "C3"]),
              "server": role("S0", ["S0", "S1", "S2"], [("s1", "S0", "S1", "?REQ"), ("s2", "S1", "S2", "!REPLYLIMIT")], ["S2"])},
    "system": sysm("C", "client", "S", "server", 2), "definitions": {}, "errata": {},
    "bindings": {"I-01": {"role": "client", "TOL": {"boundary_transition": "c3", "inclusive_cue": r"up to and including", "exclusive_cue": r"strictly less than",
        "inclusive_text": "The client MUST accept a reply received up to and including 5 seconds after the request.",
        "exclusive_text": "The client MUST accept a reply received strictly less than 5 seconds after the request."}}},
    "properties": [prop("P1", "safety", "unspecified_reception", "A reply at the 5 s boundary must be consumable."),
                   prop("P2", "functionality", "always_can_complete", "Client and server can always finish.", goal={"C": ["C2", "C3"], "S": ["S2"]})]},
  {"runs": [{"expect": {"original_status": "VIOLATION_FOUND", "final_status": "VERIFIED_SAFE_WITHIN_SCOPE", "edits": [["I-01", "inclusive"]], "checker_accepted": True}}]},
  "# tolerance_boundary\n'within 5 seconds' leaves the boundary open. The numeric value, unit and comparator are preserved on the reading. 'approximately 5 seconds' with no defined tolerance is UNANALYSED (see incomplete_coverage).\n")

# ---- MODALITY ------------------------------------------------------------------------------
w("modality_optional", "[I-01] The client MAY retransmit the request.\n[I-02] The client MUST NOT close the session before the response is received.\n", {
    "name": "Modality: MAY / MUST NOT (hypothetical)", "default_properties": ["P1", "P2"], "messages": ["REQ", "RESP"],
    "roles": {"client": role("C0", ["C0", "C1", "C2", "C3"], [("c1", "C0", "C1", "!REQ"), ("c2", "C1", "C2", "?RESP"), ("c3", "C2", "C3", "close")], ["C3"]),
              "server": role("S0", ["S0", "S1", "S2", "S3"], [("s1", "S0", "S1", "?REQ"), ("s2", "S1", "S2", "!RESP"), ("s3", "S2", "S3", "close")], ["S3"])},
    "system": sysm("C", "client", "S", "server", 2), "definitions": {}, "errata": {},
    "bindings": {
        "I-01": {"role": "client", "MODALITY": {"optional": {"id": "c_retx", "src": "C1", "dst": "C1", "action": "!REQ"}, "must_reading": "implemented",
                 "prohibit": {"type": "forbidden_action", "tid": "c_retx", "reading": "omitted"},
                 "omitted_text": "The client MUST NOT retransmit the request.", "implemented_text": "The client MUST retransmit the request."}},
        "I-02": {"role": "client", "MODALITY": {"prohibit": {"type": "required_ordering", "later": "close", "earlier": "?RESP", "impl": "C"}}}},
    "properties": [prop("P1", "safety", "no_orphan_message", "No message is pending for a closed endpoint."),
                   prop("P2", "functionality", "always_can_complete", "Both sides can close.", goal={"C": ["C3"], "S": ["S3"]})]},
  {"runs": [{"expect": {"original_status": "VIOLATION_FOUND", "final_status": "VERIFIED_SAFE_WITHIN_SCOPE", "edits": [["I-01", "omitted"]], "checker_accepted": True}}]},
  "# modality_optional\nMAY yields two readings (retransmission omitted / implemented); the implemented reading leaves a stray REQ for a closed server. MUST NOT (I-02) is modelled as a derived required-ordering safety property.\n")

# ---- ack_close derived examples -------------------------------------------------------------
ack = json.load(open(f"{D}/ack_close/model.json")); ack_spec = open(f"{D}/ack_close/spec.txt").read()
w("mixed_deployment", ack_spec, dict(ack, default_properties=["P1", "P2"]), {"runs": [{"expect": {"original_status": "VIOLATION_FOUND", "checker_accepted": True, "profile_status": {
    "ordered,enforced,ordered,enforced": "VERIFIED_SAFE_WITHIN_SCOPE", "unordered,enforced,unordered,enforced": "VERIFIED_SAFE_WITHIN_SCOPE", "ordered,enforced,unordered,enforced": "VIOLATION_FOUND"},
    "profile_class": {"ordered,enforced,unordered,enforced": "mixed", "unordered,enforced,unordered,enforced": "common-mode"}}}]},
  "# mixed_deployment\nEach implementation family passes in isolation (common-mode profiles ordered/ordered and unordered/unordered are safe) but the mixed deployment fails: one endpoint waits for an acknowledgement the other never sends.\n")
w("common_mode", ack_spec, dict(ack, default_properties=["P1", "P2"]), {"runs": [{"expect": {"original_status": "VIOLATION_FOUND", "profile_status": {
    "ordered,relaxed,ordered,relaxed": "VIOLATION_FOUND", "ordered,enforced,ordered,enforced": "VERIFIED_SAFE_WITHIN_SCOPE"}, "profile_class": {"ordered,relaxed,ordered,relaxed": "common-mode"}}}]},
  "# common_mode\nBoth endpoints share the relaxed reading of I-02 and still fail (a stray acknowledgement reaches a closed endpoint): a failure of the shared reading, not of interaction between different readings.\n")
w("multi_violation", ack_spec, dict(ack, default_properties=["P1", "P3"]), {"runs": [{"expect": {"original_status": "VIOLATION_FOUND", "final_status": "VERIFIED_SAFE_WITHIN_SCOPE", "edits": [["I-01", "ordered"], ["I-02", "enforced"]], "checker_accepted": True}}]},
  "# multi_violation\nTwo independent ambiguities each cause violations; a coordinated clarification of BOTH instructions is required (removing either edit leaves a nogood unsatisfied).\n")
w("incomplete_coverage", "[I-01] The endpoint MUST complete the acknowledgement exchange before closing the session.\n[I-02] The endpoint MUST retain the session until the peer's acknowledgement is received.\n[I-03] The endpoint SHOULD log events sensibly.\n[I-04] The endpoint waits approximately 5 seconds.\n",
  dict(ack, default_properties=["P1", "P3"], bindings=dict(ack["bindings"], **{"I-04": {"role": "endpoint", "TOL": {"boundary_transition": "t4"}}})),
  {"runs": [{"expect": {"original_status": "INCOMPLETE_UNANALYSED", "final_status": "INCOMPLETE_UNANALYSED", "unresolved_instructions": ["I-03", "I-04"]}},
            {"limits": {"max_states": 3}, "expect": {"original_status": "INCOMPLETE_UNANALYSED"}}]},
  "# incomplete_coverage\nI-03 has no model binding; I-04 uses 'approximately' with no defined tolerance. Both are UNANALYSED, so no safe verdict is issued even though the analysed part has no violation. A second run with a tiny state limit shows incomplete property checks.\n")
# ---- three_party (n-party mailbox semantics) --------------------------------------------------
w("three_party", "[I-01] After receiving the data message, the participant sends an acknowledgement and closes the session.\n", {
    "name": "Three-party coordinator/participants (synthetic)", "default_properties": ["P1", "P2"], "messages": ["DATA", "ACK"],
    "roles": {"coordinator": role("C0", ["C0", "C1", "C2", "C3", "C4", "C5"], [("c1", "C0", "C1", "!DATA@P1"), ("c2", "C1", "C2", "!DATA@P2"), ("c3", "C2", "C3", "?ACK"), ("c4", "C3", "C4", "?ACK"), ("c5", "C4", "C5", "close")], ["C5"]),
              "participant": role("Q0", ["Q0", "Q1", "Q2", "Q3"], [("q1", "Q0", "Q1", "?DATA"), ("q2", "Q1", "Q2", "!ACK@C"), ("q3", "Q2", "Q3", "close")], ["Q3"])},
    "system": {"implementations": {"C": {"role": "coordinator"}, "P1": {"role": "participant"}, "P2": {"role": "participant"}}, "channel_capacity": 2,
               "assumptions": dict(ASSUME), "mailbox": "one FIFO mailbox per implementation (sender identity not tracked); sends are addressed with !M@X"},
    "definitions": {}, "errata": {},
    "bindings": {"I-01": {"role": "participant", "ORDER": {"first": "q2", "second": "close", "role": "participant",
                 "vars": {"x": "the acknowledgement exchange", "y_gerund": "closing the session", "y_verb": "close the session"}}}},
    "properties": [prop("P1", "safety", "no_orphan_message", "No message is pending for a closed endpoint."),
                   prop("P2", "functionality", "always_can_complete", "Coordinator and both participants can always finish.", goal={"C": ["C5"], "P1": ["Q3"], "P2": ["Q3"]})]},
  {"runs": [{"expect": {"original_status": "VIOLATION_FOUND", "final_status": "VERIFIED_SAFE_WITHIN_SCOPE", "edits": [["I-01", "ordered"]], "checker_accepted": True,
                        "profile_class": {"ordered,ordered": "common-mode", "unordered,unordered": "common-mode", "ordered,unordered": "mixed", "unordered,ordered": "mixed"},
                        "profile_status": {"ordered,ordered": "VERIFIED_SAFE_WITHIN_SCOPE", "unordered,unordered": "VIOLATION_FOUND", "ordered,unordered": "VIOLATION_FOUND"}}}]},
  "# three_party\nA coordinator addresses two participants (`!DATA@P1`, `!DATA@P2`). Both participants run the same role, so reading choices are made per implementation: mixed and common-mode profiles now arise between implementations of the SAME role. Mailbox semantics: one FIFO mailbox per implementation, sender identity not tracked.\n")
print("examples written")
