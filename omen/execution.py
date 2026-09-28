from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

from .models import Probe
from .repository import baseline_test_command
from .sandbox import LocalSandbox, build_probe_harness


@dataclass
class ExecutionBundle:
    baseline: dict[str, Any]
    observations: list[dict[str, Any]]


class ExecutionPlane:
    """Deterministic execution and observation only.

    The plane may apply the candidate patch, run visible tests, and execute
    bounded probes. It never emits a merge/governance decision.
    """

    def __init__(self, sandbox: LocalSandbox):
        self.sandbox = sandbox

    def execute(
        self,
        source_repo: Path,
        patch: str | None,
        probes: list[Probe],
        *,
        current_state: bool = False,
    ) -> ExecutionBundle:
        baseline = self.run_tests(source_repo, "baseline")
        observations: list[dict[str, Any]] = [
            {"type": "baseline_health", "result": baseline},
        ]

        with tempfile.TemporaryDirectory(prefix="omen-candidate-") as temp:
            candidate_repo = Path(temp) / "candidate"
            shutil.copytree(
                source_repo,
                candidate_repo,
                ignore=shutil.ignore_patterns(".git", "__pycache__", ".omen"),
            )

            patch_status = self.apply_patch(candidate_repo, patch, current_state=current_state)
            observations.append({"type": "patch_status", **patch_status})

            if patch_status["status"] in {"applied", "current_state"}:
                candidate_tests = self.run_tests(candidate_repo, "candidate")
            else:
                candidate_tests = {
                    "version": "candidate",
                    "command": [],
                    "exit_code": 125,
                    "passed": False,
                    "skipped": True,
                    "stdout": "",
                    "stderr": "candidate tests skipped because patch application failed",
                    "duration_ms": 0,
                }
            observations.append({
                "type": "visible_tests",
                "baseline": baseline,
                "candidate": candidate_tests,
            })

            for probe in probes:
                try:
                    harness = build_probe_harness(probe)
                    base = self.sandbox.run_probe(source_repo, probe, "baseline", harness)
                    candidate = self.sandbox.run_probe(candidate_repo, probe, "candidate", harness)
                    observations.append({
                        "type": "counterfactual_probe",
                        "probe": asdict(probe),
                        "baseline": asdict(base),
                        "candidate": asdict(candidate),
                    })
                except Exception as exc:
                    observations.append({
                        "type": "counterfactual_probe",
                        "probe": asdict(probe),
                        "error": f"{type(exc).__name__}: {exc}",
                    })

        return ExecutionBundle(baseline=baseline, observations=observations)

    @staticmethod
    def apply_patch(candidate_repo: Path, patch: str | None, *, current_state: bool = False) -> dict[str, Any]:
        if not patch or not patch.strip():
            if current_state:
                return {"status": "current_state", "error": None}
            return {"status": "rejected", "error": "a patch is required unless current_state=True"}
        try:
            check = subprocess.run(
                ["git", "apply", "--check", "--whitespace=nowarn", "-"],
                cwd=candidate_repo,
                input=patch,
                text=True,
                capture_output=True,
                timeout=15,
            )
            if check.returncode != 0:
                return {"status": "rejected", "error": check.stderr.strip() or "patch failed git apply --check"}
            applied = subprocess.run(
                ["git", "apply", "--whitespace=nowarn", "-"],
                cwd=candidate_repo,
                input=patch,
                text=True,
                capture_output=True,
                timeout=15,
            )
            if applied.returncode != 0:
                return {"status": "rejected", "error": applied.stderr.strip() or "patch application failed"}
            return {"status": "applied", "error": None}
        except Exception as exc:
            return {"status": "rejected", "error": f"{type(exc).__name__}: {exc}"}

    def run_tests(self, repo: Path, version: str) -> dict[str, Any]:
        command = baseline_test_command(repo)
        if command and Path(command[0]).name in {"python", "python3", "py"}:
            command = [sys.executable, *command[1:]]
        wrapped_command, network_isolated = self.sandbox.wrap_command(command)
        start = time.monotonic()
        try:
            result = subprocess.run(
                wrapped_command,
                cwd=repo,
                env=self.sandbox.clean_environment(repo),
                capture_output=True,
                text=True,
                timeout=self.sandbox.timeout_seconds,
                preexec_fn=self.sandbox.resource_limits(),
            )
            return {
                "version": version,
                "command": command,
                "exit_code": result.returncode,
                "passed": result.returncode == 0,
                "stdout": result.stdout[-10000:],
                "stderr": result.stderr[-10000:],
                "duration_ms": int((time.monotonic() - start) * 1000),
                "network_isolation_enforced": network_isolated,
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "version": version,
                "command": command,
                "exit_code": 124,
                "passed": False,
                "timed_out": True,
                "stdout": (exc.stdout or "")[-10000:] if isinstance(exc.stdout, str) else "",
                "stderr": f"{version} visible tests timed out",
                "duration_ms": int((time.monotonic() - start) * 1000),
            }
        except (FileNotFoundError, OSError) as exc:
            return {
                "version": version,
                "command": command,
                "exit_code": 127,
                "passed": False,
                "stdout": "",
                "stderr": f"{type(exc).__name__}: {exc}",
                "duration_ms": int((time.monotonic() - start) * 1000),
            }
