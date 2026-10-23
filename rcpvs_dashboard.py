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

EXAMPLE_SPEC = "examples/ack_close/spec.txt"
EXAMPLE_MODEL = "examples/ack_close/model.json"

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


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def find_count(cert: dict, key: str):
    counts = cert.get("counts", {})
    if isinstance(counts, dict) and key in counts:
        return counts[key]
    return cert.get(key)


def checker_result() -> dict:
    """Parse the checker's JSON output (tolerates extra text around the JSON)."""
    check = st.session_state.get("last_check")
    if not check:
        return {}
    text = check.get("output", "") or ""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def checker_counts() -> dict:
    counts = checker_result().get("counts")
    return counts if isinstance(counts, dict) else {}


# Session-scoped results: never load stale artifacts left in out/strict at startup.
for _key, _default in (
    ("last_compile", None),
    ("last_check", None),
    ("active_report", ""),
    ("active_certificate", None),
):
    if _key not in st.session_state:
        st.session_state[_key] = _default

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
    st.caption("Output folder: `out/runs/<run id>/`")

# Populated only after a successful verification in this dashboard session.
report = st.session_state.get("active_report", "")
certificate = st.session_state.get("active_certificate")

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
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_dir = ROOT / "out" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    with st.spinner("Running RCPVS verification..."):
        rc, output = run_cli([
            "compile",
            "--spec", spec_path,
            "--model", model_path,
            "--out", rel(run_dir),
        ])

    report_path = run_dir / "report.md"
    cert_path = run_dir / "certificate.json"

    st.session_state["last_compile"] = {
        "rc": rc,
        "output": output,
        "time": datetime.now().astimezone().isoformat(),
        "spec": spec_path,
        "model": model_path,
        "report_path": str(report_path),
        "cert_path": str(cert_path),
    }
    st.session_state["last_check"] = None

    # Always reset first so a previous run's results can never leak into this one.
    st.session_state["active_report"] = ""
    st.session_state["active_certificate"] = None

    if rc == 0:
        st.session_state["active_report"] = read_text(report_path)
        st.session_state["active_certificate"] = read_json(cert_path)

    return rc, output


def execute_check():
    last = st.session_state.get("last_compile")

    if not last or last.get("rc") != 0:
        return 2, "No successful verification in this session. Go to New Verification first."

    cert_path = Path(last["cert_path"])

    if not cert_path.exists():
        return 2, "Certificate file not found. Run verification again."

    with st.spinner("Running the certificate checker…"):
        rc, output = run_cli(["check", rel(cert_path)])

    st.session_state["last_check"] = {
        "rc": rc,
        "output": output,
        "time": datetime.now().astimezone().isoformat(),
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

    spec_upload = model_upload = None
    input_error = None

    if source_choice == "Use Ack-Close example":
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("**Example input**")
        st.write("Uses the bundled hypothetical Ack-Close specification and model.")
        st.caption("The example is for demonstrating the tool, not a real TCP implementation test.")
        st.markdown("</div>", unsafe_allow_html=True)
        selected_ready = True
    else:
        st.markdown("**Upload input files**")
        st.caption("Upload a plain-text specification and a JSON FSM model compatible with the RCPVS CLI.")
        spec_upload = st.file_uploader("Protocol specification (.txt)", type=["txt", "md"], key="spec_upload")
        model_upload = st.file_uploader("FSM model (.json)", type=["json"], key="model_upload")

        selected_ready = False
        if spec_upload and model_upload:
            try:
                json.loads(model_upload.getvalue().decode("utf-8-sig"))
                selected_ready = True
                st.success(
                    f"Both input files are ready: **{spec_upload.name}** and **{model_upload.name}**. "
                    "Click Run verification."
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                input_error = f"The uploaded model is not valid JSON: {exc}"
                st.error(input_error)
        else:
            st.info("Choose both files to enable the run button.")

    # Optional override. Empty by default so it can NEVER silently replace the
    # selected source (the old version pre-filled these with the example paths).
    with st.expander("Advanced settings / file paths", expanded=False):
        st.caption(
            "Optional, for debugging. Leave empty to use the source selected above. "
            "If filled, the path overrides it. Paths must be relative to the project root."
        )
        spec_override = st.text_input(
            "Specification path override", value="", placeholder=EXAMPLE_SPEC, key="advanced_spec_path"
        ).strip()
        model_override = st.text_input(
            "Model path override", value="", placeholder=EXAMPLE_MODEL, key="advanced_model_path"
        ).strip()

    override_active = bool(spec_override and model_override)
    ready = override_active or selected_ready

    if override_active:
        st.warning("Path overrides are set and will be used instead of the selection above.")

    if st.button("Run verification", type="primary", disabled=not ready, use_container_width=True):
        # Resolve the paths only now, at click time.
        if override_active:
            spec_path, model_path = spec_override, model_override
        elif source_choice == "Use Ack-Close example":
            spec_path, model_path = EXAMPLE_SPEC, EXAMPLE_MODEL
        else:
            upload_dir = ROOT / "out" / "user_input" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            spec_path = rel(save_upload(spec_upload, upload_dir / "spec.txt"))
            model_path = rel(save_upload(model_upload, upload_dir / "model.json"))

        st.caption(f"Running with → specification: `{spec_path}` · model: `{model_path}`")

        rc, output = execute_compile(spec_path, model_path)
        if rc == 0:
            if st.session_state["active_report"] and st.session_state["active_certificate"] is not None:
                st.success("Pipeline command completed. Review the generated report and checker result.")
            else:
                st.warning(
                    "The command exited successfully, but no report/certificate was found in the run folder. "
                    "Check the command output below."
                )
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
        last = st.session_state.get("last_compile")
        if last:
            st.caption(f"Specification: `{last['spec']}` · Model: `{last['model']}`")
        st.download_button("Download report.md", report, file_name="report.md", mime="text/markdown")
        st.markdown(report)
    else:
        st.info("No report yet. Go to **New Verification**, select the example or upload your own protocol and model, then run verification.")
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
        st.info("No certificate yet. Go to **New Verification**, select the example or upload your own protocol and model, then run verification.")
        st.stop()
    else:
        last = st.session_state.get("last_compile")
        if last:
            st.caption(f"Specification: `{last['spec']}` · Model: `{last['model']}`")

        chk = checker_result()
        if chk.get("status") == "CERTIFICATE_ACCEPTED" or chk.get("accepted") is True:
            st.markdown(
                '<div class="cert-banner"><div class="cert-title">✓ CERTIFICATE_ACCEPTED</div>'
                '<div class="cert-sub">The independent checker accepted this certificate.</div></div>',
                unsafe_allow_html=True,
            )
        elif chk:
            st.error(f"Checker status: {chk.get('status', 'unknown')}")
        else:
            st.info("Certificate file loaded. Click **Check certificate now** to validate it.")

        st.write("")
        cc = checker_counts()

        def claim_count(key):
            if key in cc:
                return cc[key]
            v = find_count(certificate, key)
            return v if v is not None else "—"

        if not cc:
            st.caption("Claim counts appear after you run **Check certificate now**.")
        a, b, c = st.columns(3)
        a.metric("Verified claims", claim_count("verified"))
        b.metric("Rejected claims", claim_count("rejected"))
        c.metric("Unverified claims", claim_count("unverified"))

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
if last_compile and last_compile.get("rc") == 0:
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
            st.info("No report yet. Go to **New Verification**, select the example or upload your own protocol and model, then run verification.")
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
            st.info("No certificate yet. Go to **New Verification**, select the example or upload your own protocol and model, then run verification.")

st.divider()
st.caption(
    "RCPVS prototype · The bundled Ack-Close case is hypothetical. "
    "Results are limited to the supplied model, selected properties, and configured bounds."
)
