from __future__ import annotations

import json
import tempfile
from pathlib import Path

from omen.engine import OmenEngine
from omen.models import Contract, Counterexample, DecisionReport, Obligation, Probe
from omen.nemotron import NemotronClient
from omen.sandbox import LocalSandbox


class DemoNemotron(NemotronClient):
    """Deterministic stand-in for the live Token Factory call during a demo."""

    def __init__(self):
        super().__init__(offline=True)

    def analyze_contract(self, dossier):
        return Contract(
            explicit_obligations=[Obligation(
                "auth-1", "Removed users must receive 401 from protected endpoints.",
                "unknown", ["task"]
            )],
            invariants=[Obligation(
                "auth-invariant-1", "Revoked but unexpired sessions must not authorize.",
                "unknown", ["demo/auth.py:authorize"]
            )],
        )

    def plan_probes(self, dossier, contract, limit=12):
        return [Probe(
            probe_id="revoked-session",
            target_obligation_id="auth-invariant-1",
            scenario="A previously issued session is revoked while its signature remains valid.",
            inputs={"token": "revoked"},
            expected_property="protected authorization returns 401",
            severity_if_violated="critical",
            rationale="Neighboring invalid state not covered by the visible expired-session test.",
            source="demo",
        )]

    def adjudicate(self, context):
        executions = [x for x in context["executions"] if "candidate" in x]
        bad = []
        for item in executions:
            candidate = item["candidate"]
            if candidate["exit_code"] == 0 and '"status": 200' in candidate["stdout"]:
                bad.append(Counterexample(
                    title="Revoked session remains authorized",
                    status="reproduced", severity="critical",
                    scenario="Revoke a session without expiring its signature, then call the protected endpoint.",
                    observed_behavior="The candidate returns status 200 for token=revoked.",
                    expected_behavior="A revoked session must return status 401.",
                    evidence_refs=["probe:revoked-session:candidate"],
                ))
        if bad:
            return DecisionReport(
                decision="DO_NOT_MERGE",
                summary="The candidate visible test passes, but the baseline and candidate both authorize a revoked session; the patch does not remediate that pre-existing security flaw.",
                explicit_obligations=[Obligation("auth-1", "Removed users must receive 401 from protected endpoints.", "violated", ["visible-tests:candidate", "probe:revoked-session:candidate"])],
                counterexamples=bad,
                uncertainties=["The revoked-session defect is pre-existing in the baseline and remains present after the patch."],
                tested_boundary="Expired and revoked session states; local adapter; no distributed cache behavior.",
                clarifying_question=None,
                recommended_next_step="Reject the patch and require revoked-session invalidation before merge.",
            )
        return DecisionReport(
            decision="SAFE_TO_MERGE", summary="No demo counterexample reproduced within the tested boundary.",
            explicit_obligations=[Obligation("auth-1", "Removed users must receive 401 from protected endpoints.", "satisfied", ["probe:revoked-session:candidate"])],
            counterexamples=[], uncertainties=["This demo does not test distributed cache propagation."],
            tested_boundary="Expired and revoked session states; local adapter; no distributed cache behavior.",
            clarifying_question=None, recommended_next_step="Review the evidence card and merge if the boundary is acceptable.",
        )


def make_demo_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text('''SESSIONS = {
    "expired": {"valid": True, "expired": True, "revoked": False},
    "revoked": {"valid": True, "expired": False, "revoked": True},
    "active": {"valid": True, "expired": False, "revoked": False},
}

def authorize(token):
    session = SESSIONS[token]
    return 200
''')
    (repo / "test_auth.py").write_text('''from auth import authorize

def test_expired_session_is_rejected():
    assert authorize("expired") == 401
''')
    (repo / "omen_adapter.py").write_text('''from auth import authorize

def omen_probe(probe_id, inputs):
    if probe_id == "revoked-session":
        return {"status": authorize(inputs["token"])}
    raise KeyError(probe_id)
''')
    (repo / ".omen.json").write_text(json.dumps({"test_command": ["python3", "-m", "pytest", "-q"]}))
    return repo


BAD_PATCH = '''--- a/auth.py
+++ b/auth.py
@@ -7,3 +7,5 @@
 def authorize(token):
     session = SESSIONS[token]
+    if session["expired"]:
+        return 401
     return 200
'''


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="omen-demo-") as temp:
        repo = make_demo_repo(Path(temp))
        report = OmenEngine(DemoNemotron(), LocalSandbox(timeout_seconds=10), max_probes=4).evaluate(
            repo, "Prevent removed users from accessing protected projects.", BAD_PATCH
        )
        visible_tests = next(x for x in report.evidence if x.get("type") == "visible_tests")
        print("OMEN PRE-PRODUCTION DEMO")
        print("========================")
        print(f"VISIBLE TEST (candidate): {'PASS' if visible_tests['candidate']['passed'] else 'FAIL'}")
        print(f"BASELINE TEST: {'PASS' if visible_tests['baseline']['passed'] else 'FAIL'}")
        print("HIDDEN COUNTERFACTUAL: revoked session -> protected endpoint")
        print(f"DECISION: {report.decision}")
        print(report.summary)
        for c in report.counterexamples:
            print(f"COUNTEREXAMPLE: {c.title}")
            print(f"OBSERVED: {c.observed_behavior}")
            print(f"EXPECTED: {c.expected_behavior}")
        print("\nFULL REPORT")
        print(report.to_json())
        return 0 if report.decision == "DO_NOT_MERGE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
