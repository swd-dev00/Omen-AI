from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import uuid
from typing import Any

from .audit import AuditTrail
from .execution import ExecutionPlane
from .models import Contract, DecisionReport, Probe, Severity
from .nemotron import NemotronClient
from .policy import PolicyPlane
from .repository import inspect_repository
from .sandbox import LocalSandbox


class OmenEngine:
    """Coordinator for OMEN's de-hybridized three-plane architecture.

    Execution observes. Audit preserves. Policy decides. The coordinator moves
    immutable artifacts between those responsibilities without owning their
    semantics.
    """

    def __init__(
        self,
        model: NemotronClient | None = None,
        sandbox: LocalSandbox | None = None,
        max_probes: int = 12,
    ):
        self.model = model or NemotronClient()
        self.sandbox = sandbox or LocalSandbox()
        self.max_probes = max_probes
        self.execution = ExecutionPlane(self.sandbox)
        self.policy = PolicyPlane()

    def evaluate(
        self,
        repo: str | Path,
        task: str,
        patch: str | None = None,
        *,
        current_state: bool = False,
    ) -> DecisionReport:
        source_repo = Path(repo).resolve()
        if not source_repo.is_dir():
            raise ValueError(f"Repository does not exist: {source_repo}")

        trace = AuditTrail(trace_id=f"omen-{uuid.uuid4().hex[:16]}")
        dossier = inspect_repository(source_repo, task, patch)
        trace.append("EXECUTION_INTENT", {"task": task, "patch_present": bool(patch), "current_state": current_state})

        contract = self.model.analyze_contract(dossier)
        trace.append("CONTRACT_RECONSTRUCTED", asdict(contract))
        model_probes = self.model.plan_probes(dossier, contract, self.max_probes)
        probes = self._merge_probes(contract, model_probes)[: self.max_probes]
        trace.append("PROBES_PLANNED", [asdict(probe) for probe in probes])

        bundle = self.execution.execute(source_repo, patch, probes, current_state=current_state)
        for item in bundle.observations:
            trace.append(self._audit_event_type(item), item)

        context = {
            "task": task,
            "contract": asdict(contract),
            "baseline": bundle.baseline,
            "executions": bundle.observations,
            "patch": patch or dossier.get("patch", ""),
        }
        model_report = self.model.adjudicate(context)
        model_report.model_decision = model_report.decision
        model_report.evidence = bundle.observations
        trace.append("MODEL_ADJUDICATION", model_report.to_dict())

        final_report = self.policy.evaluate(model_report, bundle.baseline, bundle.observations, contract)
        trace.append("MERGE_POLICY_EVALUATED", {
            "decision": final_report.decision,
            "policy_overrides": final_report.policy_overrides,
            "policy_version": "omen-policy-v1",
        })
        if not trace.verify():
            raise RuntimeError("OMEN audit hash chain failed verification")
        final_report.audit_trace = trace.to_list()
        return final_report

    @staticmethod
    def _audit_event_type(item: dict[str, Any]) -> str:
        return {
            "baseline_health": "BASELINE_EXECUTED",
            "patch_status": "CANDIDATE_PATCH_PREPARED",
            "visible_tests": "VISIBLE_TESTS_EXECUTED",
            "counterfactual_probe": "COUNTERFACTUAL_PROBE_EXECUTED",
        }.get(str(item.get("type")), "EXECUTION_OBSERVATION")

    @staticmethod
    def _merge_probes(contract: Contract, model_probes: list[Probe]) -> list[Probe]:
        probes: list[Probe] = []
        for raw in contract.candidate_probes:
            try:
                probes.append(Probe(
                    probe_id=str(raw.get("probe_id", f"contract-{len(probes)+1}")),
                    target_obligation_id=str(raw.get("target_obligation_id", "task-1")),
                    scenario=str(raw.get("scenario", "contract probe")),
                    inputs=dict(raw.get("inputs", {})),
                    expected_property=str(raw.get("expected_property", "declared property")),
                    severity_if_violated=str(raw.get("severity_if_violated", Severity.MEDIUM.value)),
                    rationale=str(raw.get("rationale", "")),
                    source="contract",
                ))
            except (TypeError, ValueError):
                continue
        seen = {probe.probe_id for probe in probes}
        probes.extend(probe for probe in model_probes if probe.probe_id not in seen)
        return probes

    def policy_gate(self, report, baseline, executions, contract):
        return self.policy.evaluate(report, baseline, executions, contract)

    @staticmethod
    def _apply_patch(candidate_repo: Path, patch: str | None, *, current_state: bool = False):
        return ExecutionPlane.apply_patch(candidate_repo, patch, current_state=current_state)

    def _run_tests(self, repo: Path, version: str):
        return self.execution.run_tests(repo, version)


def save_report(report: DecisionReport, path: str | Path) -> None:
    Path(path).write_text(report.to_json() + "
", encoding="utf-8")
