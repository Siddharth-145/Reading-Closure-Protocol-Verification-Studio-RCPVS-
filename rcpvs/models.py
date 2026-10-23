"""Data structures required by the specification (Part 1, section 5) and status constants (Feature 9)."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# ---- Feature 9: result / coverage statuses -------------------------------------------------
VERIFIED_SAFE = "VERIFIED_SAFE_WITHIN_SCOPE"
VIOLATION = "VIOLATION_FOUND"
INCOMPLETE = "INCOMPLETE_UNANALYSED"
CERT_REJECTED = "CERTIFICATE_REJECTED"          # additional status (meaning: independent checker rejected evidence)
CLAR_UNRESOLVED = "CLARIFICATION_UNRESOLVED"    # additional status (meaning: no candidate edit set removes all violations)

# per-instruction coverage statuses
COV_ANALYSED = "ANALYSED"                # >=2 readings generated
COV_SINGLE = "ANALYSED_SINGLE"           # an operator recognised an explicit cue; exactly one reading
COV_INAPPLICABLE = "INAPPLICABLE"        # operator preconditions not met (recorded, not silently dropped)
COV_UNANALYSED = "UNANALYSED"            # outside supported operator set -> never treated as unambiguous
OPT_OPTIMAL = "OPTIMAL"; OPT_UNSAT = "UNSATISFIABLE"; OPT_LIMIT = "INCOMPLETE_LIMIT_REACHED"   # optimiser outcomes


@dataclass
class InstructionRecord:
    id: str
    text: str
    line: int
    start: int            # character span in the source document
    end: int
    role: Optional[str]
    modality: Optional[str]
    references: list = field(default_factory=list)
    errata: list = field(default_factory=list)   # user-supplied errata links only; never invented
    col: int = 1                                 # 1-based column of the span start (line-and-column span)
    text_sha256: str = ""
    negated: bool = False
    condition: Optional[str] = None              # text after if/when/unless/except (modal scope is conditional)
    actions: list = field(default_factory=list)  # crude action split of the text after the modal verb

    def to_dict(self): return asdict(self)


@dataclass
class ReadingRule:
    id: str
    operator: str
    version: str
    description: str

    def to_dict(self): return asdict(self)


@dataclass
class ReadingRecord:
    instruction_id: str
    span: tuple
    rule_id: str
    rule_version: str
    operator: str
    reading_id: str
    preconditions: list
    description: str
    patch: list                  # model change (see fsm.apply_patches)
    source_aligned: bool
    provenance: list
    status: str = COV_ANALYSED   # analysed / rejected-as-inapplicable / unresolved are kept in CoverageRecord
    clarification_text: Optional[str] = None
    original_wording: str = ""
    affected: list = field(default_factory=list)      # transitions / states / messages this reading changes
    why: str = ""                                     # why the reading was generated
    assumptions: list = field(default_factory=list)
    check_status: str = "generated"                   # generated | checked | rejected | unresolved
    numeric: Optional[dict] = None                    # preserved value/unit/comparator for TOL readings
    derived_property: Optional[dict] = None           # MUST NOT -> safety property
    cue_span: Optional[tuple] = None                  # exact character span of the cue that triggered the reading
    edit_type: str = ""

    def to_dict(self): return asdict(self)


@dataclass
class CoverageRecord:
    instruction_id: str
    rule_id: str
    status: str
    reason: str

    def to_dict(self): return asdict(self)


@dataclass
class ImplementationProfile:
    """A deployment profile: reading assignment p_i(s) for every implementation i and instruction s."""
    assignment: dict            # {"impl::instr": reading_id}
    classification: str         # "common-mode" | "mixed"
    environment: dict = field(default_factory=dict)

    def to_dict(self): return asdict(self)


@dataclass
class PropertyRecord:
    id: str
    kind: str                   # safety | functionality
    type: str
    description: str
    scope: str
    assumptions: dict
    bounds: dict

    def to_dict(self): return asdict(self)


@dataclass
class ViolationWitness:
    profile: dict
    property_id: str
    trace: list
    causal_readings: list       # readings whose tagged transitions occur in the trace
    minimal_combinations: list  # subset-minimal violating combinations (rest at baseline)
    instruction_ids: list
    rule_ids: list

    def to_dict(self): return asdict(self)


@dataclass
class ConditionalNogood:
    id: str
    literals: list              # [(impl, instruction, reading)]  -- forbidden reading combination
    condition: dict             # property ids, assumptions id, applicability
    evidence: list              # example violating profiles + traces
    scope: str

    def to_dict(self): return asdict(self)


@dataclass
class ClarificationCandidate:
    instruction_id: str
    operation: str              # "keep-reading"
    keep_reading: str
    excludes: list
    old_text: str
    new_text: str
    cost: int
    wording_len: int
    source_aligned: bool
    expected_impact: str

    def to_dict(self): return asdict(self)


@dataclass
class ConformanceTest:
    id: str
    setup: dict
    steps: list
    expected: dict
    targets: str
    assumptions: dict
    certified: bool = False

    def to_dict(self): return asdict(self)


@dataclass
class VerificationCertificate:
    body: dict

    def to_dict(self): return self.body
