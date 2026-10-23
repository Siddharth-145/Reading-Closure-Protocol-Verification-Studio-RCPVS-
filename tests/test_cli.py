"""Task 10: CLI integration tests (audit, compile, check, dot, failure modes, reproducibility)."""
import unittest, sys, os, io, json, tempfile, contextlib, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import *

SP, MP = f"{ROOT}/ack_close/spec.txt", f"{ROOT}/ack_close/model.json"
def cli(*a):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err): rc = main(list(a))
    return rc, out.getvalue(), err.getvalue()
def h(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


class Commands(unittest.TestCase):
    def test_audit_never_modifies_spec_and_writes_report(self):
        d = tempfile.mkdtemp(); rc, o, e = cli("audit", "--spec", SP, "--model", MP, "--props", "P1,P2", "--out", d)
        self.assertEqual(rc, 0); self.assertIn("final: VIOLATION_FOUND", o); self.assertTrue(os.path.isfile(f"{d}/report.md")); self.assertFalse(os.path.exists(f"{d}/revised_spec.txt")); self.assertFalse(os.path.exists(f"{d}/certificate.json"))
        self.assertIn("Recommended clarifications (audit mode", open(f"{d}/report.md").read())
    def test_compile_outputs_and_check_roundtrip(self):
        d = tempfile.mkdtemp(); rc, o, e = cli("compile", "--spec", SP, "--model", MP, "--out", d)
        self.assertEqual(rc, 0); self.assertIn("checker: CERTIFICATE_ACCEPTED", o)
        for f in ("report.md", "revised_spec.txt", "certificate.json", "conformance_tests.json"): self.assertTrue(os.path.isfile(f"{d}/{f}"), f)
        rc, o, e = cli("check", f"{d}/certificate.json"); self.assertEqual(rc, 0); self.assertEqual(json.loads(o)["status"], "CERTIFICATE_ACCEPTED")
        c = json.load(open(f"{d}/certificate.json")); c["edits"][0]["new_text"] = "[I-01] forged"; json.dump(c, open(f"{d}/forged.json", "w"))
        rc, o, e = cli("check", f"{d}/forged.json"); self.assertEqual(rc, 2); self.assertEqual(json.loads(o)["status"], CERT_REJECTED)
        tests = json.load(open(f"{d}/conformance_tests.json")); self.assertFalse(any(t["execution_status"] == "executed_against_implementation" for t in tests))
    def test_dot(self):
        rc, o, e = cli("dot", "--model", MP, "--role", "endpoint"); self.assertEqual(rc, 0); self.assertTrue(o.startswith("digraph G")); self.assertIn("t3: !ACK", o)
        rc, o, e = cli("dot", "--model", MP, "--role", "nope"); self.assertEqual(rc, 2); self.assertIn("unknown role", e)
    def test_reproducible_outputs(self):
        a, b = tempfile.mkdtemp(), tempfile.mkdtemp(); cli("compile", "--spec", SP, "--model", MP, "--out", a); cli("compile", "--spec", SP, "--model", MP, "--out", b)
        for f in ("report.md", "certificate.json", "revised_spec.txt", "conformance_tests.json"): self.assertEqual(h(f"{a}/{f}"), h(f"{b}/{f}"), f)
    def test_status_consistent_between_commands(self):
        d1, d2 = tempfile.mkdtemp(), tempfile.mkdtemp(); _, o1, _ = cli("audit", "--spec", SP, "--model", MP, "--out", d1); _, o2, _ = cli("compile", "--spec", SP, "--model", MP, "--out", d2)
        self.assertEqual(o1.split()[1], o2.split()[1])                                                                    # same original status
    def test_report_has_all_required_sections(self):
        d = tempfile.mkdtemp(); cli("compile", "--spec", SP, "--model", MP, "--out", d); r = open(f"{d}/report.md").read()
        for h_ in ("## 1. Input specification", "## 2. Model description", "## 3. Reading operators", "## 4. Alternative readings", "## 5. Deployment profiles", "## 6. Property results", "## 7. Counterexamples", "## 8. Conditional nogoods",
                   "## 9. Candidate clarifications", "## 10. Revised specification", "## 11. Behaviour preservation", "## 12. Independent checker", "## 13. Conformance tests", "## 14. Limitations", "Property policy"):
            self.assertIn(h_, r)


class Failures(unittest.TestCase):
    def fails(self, *a, frag):
        d = tempfile.mkdtemp(); rc, o, e = cli(*a, "--out", d); self.assertEqual(rc, 2, e); self.assertIn(frag, e); self.assertFalse(os.path.exists(f"{d}/report.md")); self.assertEqual(o, "")      # no misleading success output
    def test_missing_files(self):
        self.fails("audit", "--spec", "/no/spec.txt", "--model", MP, frag="specification: file not found"); self.fails("compile", "--spec", SP, "--model", "/no/model.json", frag="model: file not found")
        rc, o, e = cli("check", "/no/cert.json"); self.assertEqual(rc, 2); self.assertIn("certificate: file not found", e)
    def test_malformed_json(self):
        d = tempfile.mkdtemp(); bad = f"{d}/m.json"; open(bad, "w").write('{"roles": '); self.fails("audit", "--spec", SP, "--model", bad, frag="malformed JSON")
        open(f"{d}/c.json", "w").write("[1,"); rc, o, e = cli("check", f"{d}/c.json"); self.assertEqual(rc, 2); self.assertIn("malformed JSON", e)
    def test_invalid_model_data(self):
        d = tempfile.mkdtemp(); m = json.load(open(MP)); m["roles"]["endpoint"]["transitions"][0]["dst"] = "GHOST"; m["bindings"]["I-01"]["ORDER"]["first"] = "t77"
        json.dump(m, open(f"{d}/m.json", "w")); d2 = tempfile.mkdtemp()
        rc, o, e = cli("audit", "--spec", SP, "--model", f"{d}/m.json", "--out", d2); self.assertEqual(rc, 2); self.assertIn("transitions[t1].dst: 'GHOST'", e); self.assertIn("ORDER.first", e); self.assertFalse(os.path.exists(f"{d2}/report.md"))
    def test_unknown_property_and_operator(self):
        self.fails("audit", "--spec", SP, "--model", MP, "--props", "P1,PX", frag="unknown property id 'PX'")
        d = tempfile.mkdtemp(); m = json.load(open(MP)); m["bindings"]["I-02"]["WIBBLE"] = {}; json.dump(m, open(f"{d}/m.json", "w")); self.fails("compile", "--spec", SP, "--model", f"{d}/m.json", frag="WIBBLE: unsupported operator name")
    def test_unsupported_assumption(self):
        d = tempfile.mkdtemp(); m = json.load(open(MP)); m["system"]["assumptions"]["message_loss"] = True; json.dump(m, open(f"{d}/m.json", "w")); self.fails("audit", "--spec", SP, "--model", f"{d}/m.json", frag="message_loss")
    def test_state_limit_flag_gives_incomplete_not_success(self):
        d = tempfile.mkdtemp(); rc, o, e = cli("audit", "--spec", SP, "--model", MP, "--max-states", "3", "--props", "P1", "--out", d); self.assertEqual(rc, 0); self.assertIn("final: INCOMPLETE_UNANALYSED", o)


if __name__ == "__main__": unittest.main()
