# OMEN working web prototype

Live prototype: https://omen-hmgqez.v2.appdeploy.ai/

This directory contains the source deployed for the judge-facing OMEN prototype.

The user changes candidate authorization guards. The backend executes the baseline and candidate against the visible expired-session requirement and a revoked-session counterfactual. The backend then creates the SHA-256 hash-linked audit trace and applies the deterministic policy decision.

Default visible-test-only patch:
- visible expired-session test: PASS
- revoked-session counterfactual: FAIL
- decision: DO_NOT_MERGE

Remediated patch:
- visible expired-session test: PASS
- revoked-session counterfactual: PASS
- decision: SAFE_TO_MERGE

The Python package in the repository remains the core OMEN implementation. This web prototype exposes the same Execution -> Audit -> Policy model as an interactive judge-facing workflow.
