from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import site
import subprocess
import tempfile
import time
import uuid

try:
    import resource
except ImportError:
    resource = None

from .models import ExecutionResult, Probe


class SandboxError(RuntimeError):
    pass


class LocalSandbox:
    """Local development runner with a deliberately reduced security boundary."""

    def __init__(
        self,
        timeout_seconds: int = 30,
        output_limit: int = 100_000,
        cpu_seconds: int = 10,
        memory_bytes: int = 512 * 1024 * 1024,
        max_processes: int = 64,
    ):
        self.timeout_seconds = timeout_seconds
        self.output_limit = output_limit
        self.cpu_seconds = cpu_seconds
        self.memory_bytes = memory_bytes
        self.max_processes = max_processes
        self._network_isolation_cache: bool | None = None

    def resource_limits(self):
        if resource is None:
            return None
        cpu_seconds = self.cpu_seconds
        memory_bytes = self.memory_bytes
        max_processes = self.max_processes

        def _apply() -> None:
            for kind, value in (
                (getattr(resource, "RLIMIT_CPU", None), cpu_seconds),
                (getattr(resource, "RLIMIT_AS", None), memory_bytes),
                (getattr(resource, "RLIMIT_NPROC", None), max_processes),
            ):
                if kind is None:
                    continue
                try:
                    resource.setrlimit(kind, (value, value))
                except (ValueError, OSError):
                    pass
        return _apply

    def network_isolation_available(self) -> bool:
        if self._network_isolation_cache is None:
            probe_script = (
                "import socket,sys\n"
                "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
                "s.settimeout(2)\n"
                "try:\n"
                "    s.connect(('198.51.100.1', 80))\n"
                "    sys.exit(1)\n"
                "except OSError:\n"
                "    sys.exit(0)\n"
            )
            try:
                probe = subprocess.run(
                    ["unshare", "--net", "--", "python3", "-c", probe_script],
                    capture_output=True,
                    timeout=5,
                )
                self._network_isolation_cache = probe.returncode == 0
            except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
                self._network_isolation_cache = False
        return self._network_isolation_cache

    def wrap_command(self, command: list[str]) -> tuple[list[str], bool]:
        if self.network_isolation_available():
            return (["unshare", "--net", "--", *command], True)
        return (command, False)

    def clean_environment(self, workdir: Path | None = None) -> dict[str, str]:
        env: dict[str, str] = {}
        for name in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "WINDIR"):
            if name in os.environ:
                env[name] = os.environ[name]
        python_path = [str(workdir)] if workdir else []
        user_site = site.getusersitepackages()
        if user_site and Path(user_site).is_dir():
            python_path.append(user_site)
        env.update({
            "PYTHONPATH": os.pathsep.join(python_path),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "OMEN_NO_NETWORK": "1",
            "HOME": "/tmp/omen-home",
            "TMPDIR": "/tmp",
        })
        return env

    def run_probe(self, repo: Path, probe: Probe, version: str, harness: str) -> ExecutionResult:
        start = time.monotonic()
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        with tempfile.TemporaryDirectory(prefix=f"omen-{version}-") as temp:
            work = Path(temp) / "repo"
            shutil.copytree(repo, work, ignore=shutil.ignore_patterns(".git", "__pycache__", ".omen"))
            before = self._tree_hash(work)
            script = Path(temp) / "probe.py"
            script.write_text(harness, encoding="utf-8")
            env = self.clean_environment(work)
            command, network_isolated = self.wrap_command(["python3", str(script)])
            try:
                proc = subprocess.run(
                    command,
                    cwd=work,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    preexec_fn=self.resource_limits(),
                )
                timed_out = False
                code = proc.returncode
                stdout = proc.stdout[: self.output_limit]
                stderr = proc.stderr[: self.output_limit]
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                code = 124
                stdout = (exc.stdout or "")[-self.output_limit:] if isinstance(exc.stdout, str) else ""
                stderr = "probe timed out\n"
            after = self._tree_hash(work)
            changed = self._changed_files(before, after)
            duration_ms = int((time.monotonic() - start) * 1000)
            return ExecutionResult(
                run_id=run_id,
                version=version,
                probe_id=probe.probe_id,
                exit_code=code,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration_ms,
                timed_out=timed_out,
                network_attempted=self._looks_like_network(stderr + stdout),
                network_isolation_enforced=network_isolated,
                files_changed=changed,
                tamper_detected=any(x.startswith(".omen/") for x in changed),
            )

    @staticmethod
    def _tree_hash(root: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        for path in root.rglob("*"):
            if path.is_file():
                try:
                    result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
                except OSError:
                    pass
        return result

    @staticmethod
    def _changed_files(before: dict[str, str], after: dict[str, str]) -> list[str]:
        keys = set(before) | set(after)
        return sorted(key for key in keys if before.get(key) != after.get(key))

    @staticmethod
    def _looks_like_network(text: str) -> bool:
        needles = (
            "connection refused",
            "network is unreachable",
            "name or service not known",
            "urlopen",
            "requests.exceptions",
        )
        return any(needle in text.lower() for needle in needles)


def build_probe_harness(probe: Probe) -> str:
    payload = json.dumps({"probe_id": probe.probe_id, "inputs": probe.inputs})
    if "command" in probe.inputs:
        raise SandboxError("command probes are disabled; use omen_adapter.py")

    return """import json, importlib
payload = json.loads(%r)
try:
    mod = importlib.import_module('omen_adapter')
    result = mod.omen_probe(payload['probe_id'], payload['inputs'])
    print(json.dumps(result, sort_keys=True))
except ModuleNotFoundError:
    print('No omen_adapter.py; probe adapter is unavailable', flush=True)
    raise SystemExit(78)
""" % payload
