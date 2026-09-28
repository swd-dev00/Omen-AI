from __future__ import annotations

import argparse
from pathlib import Path

from .engine import OmenEngine, save_report
from .nemotron import NemotronClient


def main() -> int:
    parser = argparse.ArgumentParser(description="OMEN pre-mortem evaluator for coding-agent patches")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--task", required=True)
    parser.add_argument("--patch", type=Path, help="Unified diff to apply to a separate candidate checkout")
    parser.add_argument("--current-state", action="store_true", help="Explicitly inspect the current checkout without a patch")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--offline", action="store_true", help="Use deterministic fallback; no Nemotron call")
    parser.add_argument("--max-probes", type=int, default=12)
    args = parser.parse_args()
    if not args.patch and not args.current_state:
        parser.error("--patch is required unless --current-state is explicitly supplied")
    patch = args.patch.read_text(encoding="utf-8") if args.patch else None
    client = NemotronClient(offline=args.offline)
    report = OmenEngine(model=client, max_probes=args.max_probes).evaluate(
        args.repo, args.task, patch, current_state=args.current_state
    )
    print(report.to_json())
    if args.report:
        save_report(report, args.report)
    return 0 if report.decision in {"SAFE_TO_MERGE", "MERGE_WITH_CAVEAT"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
