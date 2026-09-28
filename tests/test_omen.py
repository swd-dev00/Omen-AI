from __future__ import annotations

from pathlib import Path
import json

from omen.engine import OmenEngine
from omen.models import Contract, Counterexample, Decision, DecisionReport, Obligation, Probe
from omen.nemotron import NemotronClient
from omen.sandbox import LocalSandbox, SandboxError, build_probe_harness


class MockModel(NemotronClient):
    def __init__(self, report: DecisionReport):
        super().__init__(offline=True)
        self.report = report

    def analyze_contract(self, dossier):
        return Contract(explicit_obligations=[Obligation("task-1", "The task is satisfied", "unknown", ["task"])])

    def plan_probes(self, dossier, contract, limit=12):
        return [Probe("adapter-smoke", "task-1", "adapter smoke", {}, "adapter returns successfully")]

    def adjudicate(self, context):
        return self.report


def report(decision="SAFE_TO_MERGE", counters=None):
    return DecisionReport(decision, "summary", [Obligation("task-1", "task", "satisfied", ["task"])], counters or [], [], "local adapter", None, "next")


def make_repo(tmp_path: Path, passing=True):
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n" if passing else "def test_ok():\n    assert False\n")
    (tmp_path / "omen_adapter.py").write_text("def omen_probe(probe_id, inputs):\n    return {'ok': True}\n")
    (tmp_path / ".omen.json").write_text(json.dumps({"test_command": ["python3", "-m", "pytest", "-q"]}))
    return tmp_path


def test_unhealthy_baseline_downgrades_safe(tmp_path):
    repo = make_repo(tmp_path, passing=False)
    result = OmenEngine(MockModel(report()), LocalSandbox()).evaluate(repo, "do the task")
    assert result.decision == Decision.DO_NOT_MERGE.value
    assert "baseline" in " ".join(result.policy_overrides)
    assert "candidate visible tests did not pass" in " ".join(result.policy_overrides)


def test_high_counterexample_blocks(tmp_path):
    counter = Counterexample("duplicate charge", "reproduced", "critical", "retry after timeout", "two charges", "one charge", ["probe-1"])
    result = OmenEngine(MockModel(report(counters=[counter])), LocalSandbox()).evaluate(make_repo(tmp_path), "do the task")
    assert result.decision == Decision.DO_NOT_MERGE.value


def test_shell_metacharacters_rejected():
    probe = Probe("p", "task-1", "bad", {"command": "pytest; cat secret"}, "pass")
    try:
        build_probe_harness(probe)
        assert False, "expected rejection"
    except SandboxError:
        pass


def test_patch_is_applied_to_candidate(tmp_path):
    repo = make_repo(tmp_path)
    original = (repo / "omen_adapter.py").read_text()
    patch = """--- a/omen_adapter.py
+++ b/omen_adapter.py
@@ -1,2 +1,2 @@
-def omen_probe(probe_id, inputs):
-    return {'ok': True}
+def omen_probe(probe_id, inputs):
+    return {'ok': False}
"""
    result = OmenEngine(MockModel(report()), LocalSandbox()).evaluate(repo, "do the task", patch)
    assert (repo / "omen_adapter.py").read_text() == original
    assert result.decision == Decision.SAFE_TO_MERGE.value
    visible = next(x for x in result.evidence if x.get("type") == "visible_tests")
    assert visible["candidate"]["passed"] is True


def test_candidate_visible_regression_is_blocked(tmp_path):
    repo = make_repo(tmp_path)
    patch = """--- a/test_ok.py
+++ b/test_ok.py
@@ -1,2 +1,2 @@
 def test_ok():
-    assert True
+    assert False
"""
    result = OmenEngine(MockModel(report()), LocalSandbox()).evaluate(repo, "do the task", patch)
    assert result.decision == Decision.DO_NOT_MERGE.value
    assert "candidate visible tests did not pass" in " ".join(result.policy_overrides)


def test_invalid_patch_fails_closed(tmp_path):
    result = OmenEngine(MockModel(report()), LocalSandbox()).evaluate(make_repo(tmp_path), "do the task", "not a unified diff")
    assert result.decision == Decision.DO_NOT_MERGE.value


def test_violated_explicit_obligation_fails_closed(tmp_path):
    violated = report()
    violated.explicit_obligations[0].status = "violated"
    result = OmenEngine(MockModel(violated), LocalSandbox()).evaluate(make_repo(tmp_path), "do the task")
    assert result.decision == Decision.DO_NOT_MERGE.value


def test_sandbox_does_not_inherit_api_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    env = LocalSandbox().clean_environment()
    assert "OPENAI_API_KEY" not in env
    assert "NEBIUS_API_KEY" not in env


def test_newline_command_probe_rejected():
    probe = Probe("p", "task-1", "bad", {"command": "pytest\ncat secret"}, "pass")
    try:
        build_probe_harness(probe)
        assert False, "expected rejection"
    except SandboxError:
        pass


def test_missing_patch_fails_closed(tmp_path):
    result = OmenEngine(MockModel(report()), LocalSandbox()).evaluate(make_repo(tmp_path), "do the task")
    assert result.decision == Decision.DO_NOT_MERGE.value


def test_current_state_mode_is_explicit(tmp_path):
    result = OmenEngine(MockModel(report()), LocalSandbox()).evaluate(make_repo(tmp_path), "inspect current state", current_state=True)
    assert result.decision == Decision.MERGE_WITH_CAVEAT.value


def test_unavailable_probe_fails_closed(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "omen_adapter.py").unlink()
    result = OmenEngine(MockModel(report()), LocalSandbox()).evaluate(repo, "do the task", "")
    assert result.decision in {Decision.ASK_CLARIFYING_QUESTION.value, Decision.DO_NOT_MERGE.value}


def test_resource_limits_preexec_is_safe_to_call_or_none():
    limiter = LocalSandbox().resource_limits()
    if limiter is not None:
        limiter()


def test_network_isolation_capability_check_is_cached_and_typed():
    sandbox = LocalSandbox()
    first = sandbox.network_isolation_available()
    second = sandbox.network_isolation_available()
    assert isinstance(first, bool)
    assert first == second


def test_wrap_command_reflects_isolation_capability(monkeypatch):
    sandbox = LocalSandbox()
    monkeypatch.setattr(sandbox, "network_isolation_available", lambda: True)
    wrapped, isolated = sandbox.wrap_command(["python3", "-c", "pass"])
    assert isolated is True
    assert wrapped[:2] == ["unshare", "--net"]

    monkeypatch.setattr(sandbox, "network_isolation_available", lambda: False)
    wrapped, isolated = sandbox.wrap_command(["python3", "-c", "pass"])
    assert isolated is False
    assert wrapped == ["python3", "-c", "pass"]


def test_probe_execution_result_reports_isolation_state(tmp_path):
    repo = make_repo(tmp_path)
    probe = Probe("adapter-smoke", "task-1", "adapter smoke", {}, "adapter returns successfully")
    result = LocalSandbox().run_probe(repo, probe, "baseline", build_probe_harness(probe))
    assert isinstance(result.network_isolation_enforced, bool)


def test_unknown_obligation_cannot_be_safe(tmp_path):
    unknown = report()
    unknown.explicit_obligations[0].status = "unknown"
    result = OmenEngine(MockModel(unknown), LocalSandbox()).evaluate(make_repo(tmp_path), "do the task", "")
    assert result.decision == Decision.ASK_CLARIFYING_QUESTION.value


def test_audit_plane_hash_chain_detects_tampering():
    from dataclasses import replace
    from omen.audit import AuditTrail
    trail = AuditTrail("trace-test")
    trail.append("FIRST", {"value": 1})
    trail.append("SECOND", {"value": 2})
    assert trail.verify() is True
    trail._records[0] = replace(trail._records[0], artifact_digest="0" * 64)
    assert trail.verify() is False


def test_execution_plane_has_no_merge_decision(tmp_path):
    from omen.execution import ExecutionPlane
    repo = make_repo(tmp_path)
    bundle = ExecutionPlane(LocalSandbox()).execute(repo, None, [], current_state=True)
    assert not hasattr(bundle, "decision")
    assert any(item.get("type") == "visible_tests" for item in bundle.observations)
