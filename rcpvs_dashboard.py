from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "out" / "strict"
REPORT_PATH = OUT_DIR / "report.md"
CERT_PATH = OUT_DIR / "certificate.json"

st.set_page_config(
    page_title="RCPVS | Verification Studio",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
:root { color-scheme: light; }
.stApp { background:#f6f8fc; color:#172844; }
[data-testid="stHeader"] { background:rgba(246,248,252,.96); }
[data-testid="stSidebar"] { background:#fff; border-right:1px solid #e3eaf4; }
[data-testid="stSidebar"] > div { padding-top:1.1rem; }
.brand { padding:5px 3px 17px; margin-bottom:14px; border-bottom:1px solid #e7edf5; }
.brand-icon { display:inline-flex; width:38px; height:38px; align-items:center; justify-content:center;
border-radius:11px; background:#eaf2ff; color:#1769e0; font-size:1.2rem; font-weight:800; margin-right:9px; }
.brand-name { color:#14294d; font-size:1.25rem; font-weight:800; vertical-align:middle; }
.brand-sub { color:#71809a; font-size:.78rem; line-height:1.45; margin-top:8px; }
.hero { padding:23px 27px; border:1px solid #dce7f6; border-radius:17px;
background:linear-gradient(110deg,#fff 0%,#eff6ff 100%); margin-bottom:20px;
box-shadow:0 4px 18px rgba(28,64,120,.035); }
.eyebrow { color:#216fe8; font-size:.75rem; letter-spacing:.12em; font-weight:800; }
.hero h1 { color:#13264a; font-size:1.9rem; margin:.5rem 0 .4rem; }
.hero p { color:#647792; margin:0; }
.section-title { color:#172b4d; font-size:1.12rem; font-weight:800; margin:.2rem 0; }
.section-sub { color:#72819a; font-size:.85rem; margin-bottom:12px; }
.panel { background:#fff; border:1px solid #e0e8f3; border-radius:14px; padding:16px;
box-shadow:0 3px 12px rgba(25,55,100,.03); }
.stepper { display:flex; gap:0; align-items:flex-start; background:#fff; border:1px solid #e0e8f3;
border-radius:14px; padding:18px 10px 12px; }
.step { flex:1; text-align:center; position:relative; padding:0 7px; }
.step:not(:last-child):after { content:""; position:absolute; top:16px; left:60%; width:80%; height:2px; background:#dce6f5; z-index:0; }
.step-dot { position:relative; z-index:1; width:33px; height:33px; border-radius:50%;
display:inline-flex; align-items:center; justify-content:center; font-weight:800;
background:#edf2f8; color:#71809a; border:1px solid #d9e2ee; }
.step.done .step-dot { background:#e3f7ef; color:#07865e; border-color:#9bdfc3; }
.step.active .step-dot { background:#e8f1ff; color:#1769e0; border:2px solid #77a9ff; }
.step-title { color:#243956; font-size:.82rem; font-weight:750; margin-top:9px; }
.step-sub { color:#7887a0; font-size:.72rem; margin-top:4px; line-height:1.35; }
div[data-testid="stMetric"] { background:#fff; border:1px solid #e0e8f3; padding:13px 15px; border-radius:12px; }
div[data-testid="stMetricLabel"] { color:#6d7d96; }
div[data-testid="stMetricValue"] { color:#162b4e; font-size:1.25rem; }
.stButton > button,.stDownloadButton > button { border-radius:9px; min-height:2.55rem; font-weight:650; }
.stButton > button[kind="primary"] { background:#216fe8; border-color:#216fe8; }
div[data-testid="stCode"],.stCode { border:1px solid #e1e8f1; border-radius:10px; }
.small-muted { color:#74839b; font-size:.8rem; }
.cert-banner { border:1px solid #b8e8d2; background:#f0fbf6; border-radius:14px; padding:18px; }
.cert-title { color:#08794f; font-size:1.1rem; font-weight:800; }
.cert-sub { color:#4f7568; font-size:.86rem; margin-top:4px; }
</style>
""", unsafe_allow_html=True)


def run_cli(args: list[str], stdin_text: str | None = None) -> tuple[int, str]:
    command = [sys.executable, "-X", "utf8", "-m", "rcpvs.cli", *args]
    try:
        result = subprocess.run(
            command, cwd=ROOT, input=stdin_text, text=True, encoding="utf-8",
            errors="replace", capture_output=True, timeout=180,
        )
        output = result.stdout or ""
        if result.stderr:
            output += ("\n" if output else "") + result.stderr
        return result.returncode, output.strip()
    except subprocess.TimeoutExpired:
        return 124, "Command timed out after 180 seconds."
    except Exception as exc:
        return 1, f"{type(exc).__name__}: {exc}"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    except OSError:
        return ""


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except (OSError, json.JSONDecodeError):
        return None


def save_upload(upload, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(upload.getvalue())
    return destination


def find_count(cert: dict, key: str):
    counts = cert.get("counts", {})
    if isinstance(counts, dict) and key in counts:
        return counts[key]
    return cert.get(key)


# Session values preserve the latest run even after Streamlit reruns.
if "selected_spec" not in st.session_state:
    st.session_state["selected_spec"] = "example"
if "last_compile" not in st.session_state:
    st.session_state["last_compile"] = None
if "last_check" not in st.session_state:
    st.session_state["last_check"] = None

with st.sidebar:
    st.markdown("""
    <div class="brand">
      <span class="brand-icon">⌘</span><span class="brand-name">RCPVS</span>
      <div class="brand-sub">Reading-Closure Protocol<br>Verification Studio</div>
    </div>
    """, unsafe_allow_html=True)
    page = st.radio(
        "Workspace",
        ["Dashboard", "New Verification", "Report", "Certificate", "About"],
        label_visibility="visible",
    )
    st.divider()
    st.markdown("**Workspace status**")
    st.caption("Local prototype · Files stay in your project folder")
    st.caption("Output folder: `out/strict/`")

report = read_text(REPORT_PATH)
certificate = read_json(CERT_PATH)
if st.session_state.get("last_compile"):
    report = read_text(REPORT_PATH) or report
if st.session_state.get("last_check"):
    certificate = read_json(CERT_PATH) or certificate

st.markdown("""
<div class="hero">
  <div class="eyebrow">PROTOCOL ANALYSIS · MODEL CHECKING · CERTIFICATES</div>
  <h1>Reading-Closure Protocol Verification Studio</h1>
  <p>Analyze alternative protocol readings, detect model violations, clarify requirements, and inspect verification certificates.</p>
</div>
""", unsafe_allow_html=True)


def show_stepper(active: int, completed: set[int] | None = None):
    completed = completed or set()
    steps = [
        ("Specification", "Text + FSM model"),
        ("Readings", "Alternative interpretations"),
        ("Verification", "Profiles + properties"),
        ("Clarification", "Candidate edits"),
        ("Certificate", "Re-check + result"),
    ]
    parts = ['<div class="stepper">']
    for i, (title, subtitle) in enumerate(steps, start=1):
        cls = "done" if i in completed else ("active" if i == active else "")
        marker = "✓" if i in completed else str(i)
        parts.append(
            f'<div class="step {cls}"><div class="step-dot">{marker}</div>'
            f'<div class="step-title">{title}</div><div class="step-sub">{subtitle}</div></div>'
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def execute_compile(spec_path: str, model_path: str):
    with st.spinner("Running RCPVS analysis and bounded re-verification…"):
        rc, output = run_cli([
            "compile", "--spec", spec_path, "--model", model_path, "--out", "out/strict"
        ])
    st.session_state["last_compile"] = {
        "rc": rc, "output": output, "time": datetime.now().astimezone().isoformat(),
        "spec": spec_path, "model": model_path,
    }
    st.session_state["last_check"] = None
    return rc, output


def execute_check():
    with st.spinner("Running the certificate checker…"):
        rc, output = run_cli(["check", "out/strict/certificate.json"])
    st.session_state["last_check"] = {
        "rc": rc, "output": output, "time": datetime.now().astimezone().isoformat()
    }
    return rc, output


if page == "New Verification":
    st.markdown('<div class="section-title">New verification run</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Choose the example or provide your own specification and FSM model.</div>', unsafe_allow_html=True)
    source_choice = st.radio(
        "Input source",
        ["Use Ack-Close example", "Upload my own files"],
        horizontal=True,
        key="input_source_choice",
    )

    spec_path, model_path = None, None
    if source_choice == "Use Ack-Close example":
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("**Example input**")
        st.write("Uses the bundled hypothetical Ack-Close specification and model.")
        st.caption("The example is for demonstrating the tool, not a real TCP implementation test.")
        st.markdown("</div>", unsafe_allow_html=True)
        spec_path = "examples/ack_close/spec.txt"
        model_path = "examples/ack_close/model.json"
    else:
        st.markdown("**Upload input files**")
        st.caption("Upload a plain-text specification and a JSON FSM model compatible with the RCPVS CLI.")
        spec_upload = st.file_uploader("Protocol specification (.txt)", type=["txt", "md"], key="spec_upload")
        model_upload = st.file_uploader("FSM model (.json)", type=["json"], key="model_upload")
        if spec_upload and model_upload:
            custom_dir = ROOT / "out" / "user_input"
            spec_path = str(save_upload(spec_upload, custom_dir / "spec.txt").relative_to(ROOT)).replace("\\", "/")
            model_path = str(save_upload(model_upload, custom_dir / "model.json").relative_to(ROOT)).replace("\\", "/")
            st.success("Both input files are ready. Review the filenames, then run verification.")
        else:
            st.info("Choose both files to enable the run button.")

    with st.expander("Advanced settings / file paths", expanded=False):
        st.caption("For debugging only. Paths must be relative to the project root.")
        spec_path = st.text_input("Specification path", value=spec_path or "", key="advanced_spec_path")
        model_path = st.text_input("Model path", value=model_path or "", key="advanced_model_path")

    ready = bool(spec_path and model_path)
    if st.button("Run verification", type="primary", disabled=not ready, use_container_width=True):
        rc, output = execute_compile(spec_path, model_path)
        if rc == 0:
            st.success("Pipeline command completed. Review the generated report and checker result.")
        else:
            st.error(f"Pipeline command failed (exit code {rc}).")
        st.code(output or "(No command output)", language="text")
        if rc == 0:
            st.info("Next: open Report, then Certificate and run Check certificate.")
    st.stop()


if page == "Report":
    st.markdown('<div class="section-title">Verification report</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">The generated Markdown report from the most recent compile run.</div>', unsafe_allow_html=True)
    if report:
        st.download_button("Download report.md", report, file_name="report.md", mime="text/markdown")
        st.markdown(report)
    else:
        st.info("No report is available yet. Open New Verification and run the pipeline.")
    st.stop()


if page == "Certificate":
    st.markdown('<div class="section-title">Verification certificate</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">A readable summary of the certificate, with the original JSON available for inspection.</div>', unsafe_allow_html=True)

    if st.button("Check certificate now", type="primary"):
        rc, output = execute_check()
        if rc == 0 and "CERTIFICATE_ACCEPTED" in output:
            st.success("Certificate checker reports CERTIFICATE_ACCEPTED.")
        elif rc != 0:
            st.error(f"Checker command failed (exit code {rc}).")
        else:
            st.info("Checker completed. Review its output below.")

    check = st.session_state.get("last_check")
    if check:
        st.markdown("**Latest checker output**")
        st.code(check["output"] or "(No output)", language="json")

    if certificate is None:
        st.warning("Certificate file not found. Run a verification first.")
    else:
        counts = certificate.get("counts", {}) if isinstance(certificate, dict) else {}
        status = certificate.get("status", "Status not included") if isinstance(certificate, dict) else "Unknown"
        accepted = certificate.get("accepted") if isinstance(certificate, dict) else None
        if status == "CERTIFICATE_ACCEPTED" or accepted is True:
            st.markdown(
                '<div class="cert-banner"><div class="cert-title">✓ Certificate checker acceptance recorded</div>'
                '<div class="cert-sub">See the checker output below for the authoritative result.</div></div>',
                unsafe_allow_html=True,
            )
        else:
            st.info(f"Certificate file loaded. Status: {status}. Run the checker to validate it.")

        st.write("")
        a, b, c = st.columns(3)
        a.metric("Verified claims", find_count(certificate, "verified") if find_count(certificate, "verified") is not None else "—")
        b.metric("Rejected claims", find_count(certificate, "rejected") if find_count(certificate, "rejected") is not None else "—")
        c.metric("Unverified claims", find_count(certificate, "unverified") if find_count(certificate, "unverified") is not None else "—")

        st.download_button(
            "Download certificate JSON",
            json.dumps(certificate, indent=2, ensure_ascii=False),
            file_name="certificate.json",
            mime="application/json",
        )
        with st.expander("Inspect raw certificate JSON"):
            st.json(certificate)
    st.caption("The summary presents the generated certificate data. The checker output determines whether the checker accepted it.")
    st.stop()


if page == "About":
    st.markdown('<div class="section-title">About RCPVS</div>', unsafe_allow_html=True)
    st.write(
        "RCPVS is a prototype for analyzing alternative readings of protocol instructions, checking a supplied finite-state model, "
        "proposing clarification edits, and validating a generated certificate."
    )
    st.warning(
        "The bundled Ack-Close case is hypothetical. VERIFIED_SAFE_WITHIN_SCOPE applies only to the supplied model, "
        "selected properties, and configured bounds. It is not evidence that a real TCP implementation was tested."
    )
    st.stop()


# Dashboard home
st.markdown('<div class="section-title">Verification workflow</div>', unsafe_allow_html=True)
st.markdown('<div class="section-sub">A connected overview of the steps performed by the prototype.</div>', unsafe_allow_html=True)

last_compile = st.session_state.get("last_compile")
last_check = st.session_state.get("last_check")
completed = set()
active = 1
if last_compile:
    completed = {1, 2, 3, 4}
    active = 5
if last_check and last_check.get("rc") == 0 and "CERTIFICATE_ACCEPTED" in last_check.get("output", ""):
    completed = {1, 2, 3, 4, 5}
    active = 5
show_stepper(active, completed)

st.write("")
st.markdown('<div class="section-title">Latest results</div>', unsafe_allow_html=True)
st.markdown('<div class="section-sub">Statuses are based on the generated report and actual checker output available to this dashboard.</div>', unsafe_allow_html=True)

original, final = "Not available", "Not available"
for line in report.splitlines():
    if "Original status:" in line and "VIOLATION_FOUND" in line:
        original = "VIOLATION_FOUND"
    if "final status" in line.lower() and "VERIFIED_SAFE_WITHIN_SCOPE" in line:
        final = "VERIFIED_SAFE_WITHIN_SCOPE"
    if "Re-verification status" in line and "VERIFIED_SAFE_WITHIN_SCOPE" in line:
        final = "VERIFIED_SAFE_WITHIN_SCOPE"
if "VERIFIED_SAFE_WITHIN_SCOPE" in report and final == "Not available":
    final = "VERIFIED_SAFE_WITHIN_SCOPE"

if last_compile:
    output = last_compile["output"]
    if "VIOLATION_FOUND" in output:
        original = "VIOLATION_FOUND"
    if "VERIFIED_SAFE_WITHIN_SCOPE" in output:
        final = "VERIFIED_SAFE_WITHIN_SCOPE"

checker_output = last_check["output"] if last_check else ""
checker_status = "CERTIFICATE_ACCEPTED" if "CERTIFICATE_ACCEPTED" in checker_output else "Not checked this session"

a, b, c = st.columns(3)
a.metric("Original analysis", original)
b.metric("Re-verification", final)
c.metric("Certificate checker", checker_status)

left, right = st.columns(2)
with left:
    with st.container(border=True):
        st.markdown("**Run verification**")
        st.caption("Choose a bundled example or upload a specification and compatible JSON FSM model.")
        if st.button("Open new verification", type="primary", use_container_width=True):
            st.session_state["nav_to_new"] = True
            st.rerun()
with right:
    with st.container(border=True):
        st.markdown("**Check certificate**")
        st.caption("Run the certificate checker against the generated certificate file.")
        if st.button("Check certificate", use_container_width=True):
            rc, output = execute_check()
            if rc == 0 and "CERTIFICATE_ACCEPTED" in output:
                st.success("Certificate checker accepted the certificate.")
            elif rc != 0:
                st.error(f"Checker command failed (exit code {rc}).")
            st.code(output or "(No output)", language="json")

if st.session_state.pop("nav_to_new", False):
    st.info("Choose **New Verification** from the sidebar to select your input files.")

if last_compile:
    with st.expander("Last compile output", expanded=False):
        st.caption(f"Specification: {last_compile['spec']} · Model: {last_compile['model']}")
        st.code(last_compile["output"] or "(No output)", language="text")
if last_check:
    with st.expander("Last certificate-check output", expanded=False):
        st.code(last_check["output"] or "(No output)", language="json")

col1, col2 = st.columns([1.2, 1])
with col1:
    with st.container(border=True):
        st.markdown("**Verification report**")
        if report:
            st.caption("Generated report available")
            st.download_button("Download report.md", report, file_name="report.md", mime="text/markdown", key="home_report_download")
            with st.expander("Preview report"):
                st.markdown(report)
        else:
            st.caption("No report yet. Run a verification first.")
with col2:
    with st.container(border=True):
        st.markdown("**Certificate**")
        if certificate is not None:
            st.caption("Certificate JSON available")
            st.download_button(
                "Download certificate.json",
                json.dumps(certificate, indent=2, ensure_ascii=False),
                file_name="certificate.json",
                mime="application/json",
                key="home_cert_download",
            )
            with st.expander("Preview certificate JSON"):
                st.json(certificate)
        else:
            st.caption("No certificate yet. Run a verification first.")

st.divider()
st.caption(
    "RCPVS prototype · The bundled Ack-Close case is hypothetical. "
    "Results are limited to the supplied model, selected properties, and configured bounds."
)
