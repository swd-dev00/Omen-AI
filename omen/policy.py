from __future__ import annotations

from typing import Any

from .models import Contract, Decision, DecisionReport, Severity, Status


class PolicyPlane:
    """Deterministic governance over preserved observations.

    This is the only OMEN plane permitted to change the final merge decision.
    """

    def evaluate(
        self,
        report: DecisionReport,
        baseline: dict[str, Any],
        observations: list[dict[str, Any]],
        contract: Contract,
    ) -> DecisionReport:
        overrides: list[str] = []
        report.evidence = observations
        probe_items = [item for item in observations if item.get("type") == "counterfactual_probe"]
        isolated_sides = [
            item.get(side, {}).get("network_isolation_enforced", False)
            for item in probe_items
            for side in ("baseline", "candidate")
            if item.get(side)
        ]
        if probe_items:
            if isolated_sides and all(isolated_sides):
                report.uncertainties.append(
                    "Probe execution used kernel-enforced network-namespace denial (unshare --net), "
                    "verified by a live connection-attempt check at sandbox startup. This is a real "
                    "runtime control on hosts that support it, not a string-matching heuristic, but it "
                    "still runs on a shared local machine rather than a dedicated container or VM."
                )
            else:
                report.uncertainties.append(
                    "Kernel-level network-namespace denial was unavailable on this host for at least one "
                    "probe run, so network monitoring for it fell back to output-string heuristics; "
                    "production use requires a host or container where runtime-level network denial is "
                    "guaranteed to bind."
                )

        patch_status = next((x for x in observations if x.get("type") == "patch_status"), None)
        if not patch_status or patch_status.get("status") not in {"applied", "current_state"}:
            report.decision = Decision.DO_NOT_MERGE.value
            overrides.append("patch was missing, rejected, or current-state mode was not explicit")
        elif patch_status.get("status") == "current_state":
            report.uncertainties.append(
                "Current-state inspection was explicitly requested, so no baseline-to-patch merge claim can be established."
            )
            if report.decision == Decision.SAFE_TO_MERGE.value:
                report.decision = Decision.MERGE_WITH_CAVEAT.value
                overrides.append("current-state inspection cannot establish SAFE_TO_MERGE without a candidate patch")

        visible = next((x for x in observations if x.get("type") == "visible_tests"), None)
        if not visible or not visible.get("candidate", {}).get("passed", False):
            report.decision = Decision.DO_NOT_MERGE.value
            overrides.append("candidate visible tests did not pass or were not executed")

        if not baseline.get("passed", False):
            report.uncertainties.append(
                "Baseline visible tests did not pass; pre-existing and candidate failures must be distinguished."
            )
            overrides.append("baseline was already unhealthy")
            if report.decision == Decision.SAFE_TO_MERGE.value:
                report.decision = Decision.MERGE_WITH_CAVEAT.value

        if not probe_items:
            report.decision = Decision.DO_NOT_MERGE.value
            overrides.append("no counterfactual probes were executed")
        for item in probe_items:
            if "error" in item or not item.get("baseline") or not item.get("candidate"):
                report.decision = Decision.DO_NOT_MERGE.value
                overrides.append("counterfactual probe failed to execute")
                continue
            for side in ("baseline", "candidate"):
                result = item.get(side)
                if not result:
                    continue
                if result.get("exit_code") == 78 or result.get("timed_out"):
                    report.decision = Decision.DO_NOT_MERGE.value
                    overrides.append("counterfactual probe returned an unavailable or incomplete result")
                if result.get("tamper_detected") or result.get("network_attempted"):
                    report.decision = Decision.DO_NOT_MERGE.value
                    overrides.append(f"sandbox integrity violation in {side} probe")

        reproduced = [
            counter for counter in report.counterexamples
            if counter.status == "reproduced"
            and counter.severity in {Severity.HIGH.value, Severity.CRITICAL.value}
        ]
        if reproduced:
            report.decision = Decision.DO_NOT_MERGE.value
            overrides.append("reproducible high/critical counterexample")

        obligations = report.explicit_obligations
        unknown_or_unevidenced = [
            obligation for obligation in obligations
            if obligation.status != Status.SATISFIED.value or not obligation.evidence_refs
        ]
        violated_ids = {
            obligation.id for obligation in obligations
            if obligation.status == Status.VIOLATED.value
        }
        if violated_ids:
            report.decision = Decision.DO_NOT_MERGE.value
            overrides.append("model reported a violated explicit obligation")
        elif unknown_or_unevidenced:
            report.decision = Decision.ASK_CLARIFYING_QUESTION.value
            overrides.append("explicit obligations were unknown, omitted, or unevidenced")
            report.uncertainties.append("Every explicit obligation requires satisfied status and evidence references.")

        if report.decision == Decision.SAFE_TO_MERGE.value and not report.explicit_obligations:
            report.decision = Decision.ASK_CLARIFYING_QUESTION.value
            overrides.append("no explicit obligation was established")

        if report.decision == Decision.ASK_CLARIFYING_QUESTION.value and not report.clarifying_question:
            report.clarifying_question = (
                "Which observable behavior should be treated as the acceptance criterion for this change?"
            )

        report.policy_overrides.extend(dict.fromkeys(overrides))
        return report
