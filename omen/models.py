from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any
import json


class Decision(str, Enum):
    SAFE_TO_MERGE = "SAFE_TO_MERGE"
    MERGE_WITH_CAVEAT = "MERGE_WITH_CAVEAT"
    ASK_CLARIFYING_QUESTION = "ASK_CLARIFYING_QUESTION"
    DO_NOT_MERGE = "DO_NOT_MERGE"


class Status(str, Enum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Obligation:
    id: str
    statement: str
    status: str = Status.UNKNOWN.value
    evidence_refs: list[str] = field(default_factory=list)


@dataclass
class Counterexample:
    title: str
    status: str
    severity: str
    scenario: str
    observed_behavior: str
    expected_behavior: str
    evidence_refs: list[str] = field(default_factory=list)


@dataclass
class Contract:
    explicit_obligations: list[Obligation] = field(default_factory=list)
    implied_obligations: list[Obligation] = field(default_factory=list)
    invariants: list[Obligation] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    candidate_probes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Probe:
    probe_id: str
    target_obligation_id: str
    scenario: str
    inputs: dict[str, Any]
    expected_property: str
    severity_if_violated: str = Severity.MEDIUM.value
    rationale: str = ""
    source: str = "model"


@dataclass
class ExecutionResult:
    run_id: str
    version: str
    probe_id: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    network_attempted: bool = False
    network_isolation_enforced: bool = False
    files_changed: list[str] = field(default_factory=list)
    tamper_detected: bool = False

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.tamper_detected


@dataclass
class DecisionReport:
    decision: str
    summary: str
    explicit_obligations: list[Obligation]
    counterexamples: list[Counterexample]
    uncertainties: list[str]
    tested_boundary: str
    clarifying_question: str | None
    recommended_next_step: str
    model_decision: str | None = None
    policy_overrides: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    audit_trace: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def _require(obj: dict[str, Any], key: str, typ: type | tuple[type, ...]) -> Any:
    if key not in obj or not isinstance(obj[key], typ):
        raise ValueError(f"Missing or invalid field: {key}")
    return obj[key]


def contract_from_json(obj: dict[str, Any]) -> Contract:
    def obligations(name: str) -> list[Obligation]:
        result = []
        for raw in obj.get(name, []):
            result.append(Obligation(
                id=_require(raw, "id", str),
                statement=_require(raw, "statement", str),
                status=raw.get("status", Status.UNKNOWN.value),
                evidence_refs=list(raw.get("evidence_refs", [])),
            ))
        return result
    return Contract(
        explicit_obligations=obligations("explicit_obligations"),
        implied_obligations=obligations("implied_obligations"),
        invariants=obligations("invariants"),
        non_goals=list(obj.get("non_goals", [])),
        ambiguities=list(obj.get("ambiguities", [])),
        candidate_probes=list(obj.get("candidate_probes", [])),
    )


def probe_from_json(obj: dict[str, Any]) -> Probe:
    return Probe(
        probe_id=_require(obj, "probe_id", str),
        target_obligation_id=_require(obj, "target_obligation_id", str),
        scenario=_require(obj, "scenario", str),
        inputs=obj.get("inputs", {}),
        expected_property=_require(obj, "expected_property", str),
        severity_if_violated=obj.get("severity_if_violated", Severity.MEDIUM.value),
        rationale=obj.get("rationale", ""),
        source=obj.get("source", "model"),
    )


def report_from_json(obj: dict[str, Any]) -> DecisionReport:
    allowed = {d.value for d in Decision}
    decision = _require(obj, "decision", str)
    if decision not in allowed:
        raise ValueError(f"Invalid decision: {decision}")
    obligations = [Obligation(
        id=_require(x, "id", str), statement=_require(x, "statement", str),
        status=x.get("status", Status.UNKNOWN.value), evidence_refs=list(x.get("evidence_refs", [])))
        for x in obj.get("explicit_obligations", [])]
    counters = [Counterexample(
        title=_require(x, "title", str), status=_require(x, "status", str),
        severity=_require(x, "severity", str), scenario=_require(x, "scenario", str),
        observed_behavior=_require(x, "observed_behavior", str),
        expected_behavior=_require(x, "expected_behavior", str),
        evidence_refs=list(x.get("evidence_refs", [])))
        for x in obj.get("counterexamples", [])]
    return DecisionReport(
        decision=decision, summary=_require(obj, "summary", str),
        explicit_obligations=obligations, counterexamples=counters,
        uncertainties=list(obj.get("uncertainties", [])),
        tested_boundary=_require(obj, "tested_boundary", str),
        clarifying_question=obj.get("clarifying_question"),
        recommended_next_step=_require(obj, "recommended_next_step", str),
    )
