"""Executes generated conformance tests against a REAL TCP stack (the operating system's, via Python sockets on loopback).

This is external execution: the system under test is not the verified model. Mapping (see MODELLING.md):
  S !DATA -> send();  R ?DATA -> data present in R's socket (MSG_PEEK, not consumed);  R read -> recv();  R close -> close();
  R !FIN / R !RST -> kernel events with no application call; they are checked only through the sender's next recv():
  S ?FIN -> recv() returns b"";  S ?RST -> recv() raises ConnectionResetError.
Pass semantics (stated, not implicit):
  normal_success_coverage   : passed  iff the implementation REPRODUCES the model sequence in every repetition
  counterexample / clarification_regression : passed iff the implementation does NOT reproduce the unsafe/removed sequence in every repetition
  mixed outcomes across repetitions -> passed = None (flaky, no verdict)."""
from __future__ import annotations
import json, platform, select, socket, subprocess, time

MAPPABLE = {("S", "!DATA"), ("R", "?DATA"), ("R", "read"), ("R", "close"), ("R", "!FIN"), ("R", "!RST"), ("S", "?FIN"), ("S", "?RST")}
EXECUTABLE_KINDS = ("normal_success_coverage", "counterexample", "clarification_regression")


def environment():
    try: kernel = subprocess.run(["uname", "-a"], capture_output=True, text=True).stdout.strip()
    except Exception: kernel = "unknown"
    return {"platform": platform.platform(), "python": platform.python_version(), "uname": kernel, "transport": "TCP over 127.0.0.1 loopback via the socket API",
            "note": "single host, single kernel, observations are socket-API-level (not packet captures)"}


def _pair():
    ls = socket.socket(); ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); ls.bind(("127.0.0.1", 0)); ls.listen(1)
    s = socket.socket(); s.connect(ls.getsockname()); r, _ = ls.accept(); ls.close(); return s, r


def run_once(steps, timeout=2.0):
    s, r = _pair(); obs, reproduced = [], True
    try:
        for st in steps:
            impl, act = st["impl"], st["action"]
            if (impl, act) not in MAPPABLE: raise ValueError(f"unmappable step {impl} {act}")
            if (impl, act) == ("S", "!DATA"): s.sendall(b"DATA"); ev = "sent"
            elif (impl, act) == ("R", "?DATA"):
                end, got = time.time() + timeout, b""
                while time.time() < end and got != b"DATA":
                    if select.select([r], [], [], 0.05)[0]: got = r.recv(4, socket.MSG_PEEK)
                ev = "pending" if got == b"DATA" else "MISSING"
                if ev == "MISSING": reproduced = False
            elif (impl, act) == ("R", "read"): ev = "read:" + repr(r.recv(4))
            elif (impl, act) == ("R", "close"): r.close(); r = None; ev = "closed"
            elif impl == "R": ev = "kernel event (observed via S)"
            else:
                s.settimeout(timeout)
                try: d = s.recv(16); ev = "FIN" if d == b"" else f"DATA:{d!r}"
                except ConnectionResetError: ev = "RST"
                except socket.timeout: ev = "TIMEOUT"
                if ev != act[1:]: reproduced = False
            obs.append({"impl": impl, "action": act, "observed": ev})
            if not reproduced: break
    finally:
        for x in (s, r):
            try: x and x.close()
            except Exception: pass
    return {"reproduced": reproduced, "observations": obs}


def execute(tests, mark_executed, repeats=5, timeout=2.0):
    env, records = environment(), []
    for t in tests:
        if t["kind"] not in EXECUTABLE_KINDS or not t["steps"]: continue
        if any((x["impl"], x["action"]) not in MAPPABLE for x in t["steps"]):
            records.append({"test_id": t["id"], "kind": t["kind"], "executed": False, "reason": "contains actions the harness cannot map to the socket API"}); continue
        runs = [run_once(t["steps"], timeout) for _ in range(repeats)]
        n = sum(r["reproduced"] for r in runs)
        expect_repro = t["kind"] == "normal_success_coverage"
        passed = (expect_repro if n == repeats else (not expect_repro if n == 0 else None))
        rec = {"test_id": t["id"], "kind": t["kind"], "targets": t["targets"], "executed": True, "repeats": repeats, "reproduced_count": n,
               "passed": passed, "pass_semantics": "model sequence must be reproduced" if expect_repro else "unsafe/removed sequence must NOT be reproduced",
               "first_run_observations": runs[0]["observations"], "implementation": "OS TCP stack via sockets (see environment)", "environment": env}
        mark_executed(tests, t["id"], passed, rec["implementation"], f"{n}/{repeats} repetitions reproduced the model sequence", reproduced_count=n, repeats=repeats, environment=env, observations=runs[0]["observations"])
        records.append(rec)
    return records
