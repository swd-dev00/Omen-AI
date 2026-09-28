# OMEN working web prototype

Live prototype: https://omen-hmgqez.v2.appdeploy.ai/

This directory contains the source deployed for the judge-facing OMEN prototype.

## What the live build does

The prototype follows the same flow described in the root README:

Execution Plane -> Audit Plane -> Policy Plane

A judge provides:

- a task contract
- a proposed unified diff against the built-in `auth.py` fixture

OMEN then:

1. reconstructs the visible obligation and bounded neighboring state;
2. executes the baseline authorization behavior;
3. applies the recognized candidate patch;
4. executes the visible expired-session test;
5. executes the revoked-but-unexpired counterfactual;
6. preserves the evidence in a SHA-256 hash-linked audit trace;
7. applies the deterministic Policy Plane.

### README demo patch

- visible expired-session test: PASS
- revoked-session counterfactual: FAIL
- observed revoked-session status: 200
- expected revoked-session status: 401
- decision: `DO_NOT_MERGE`

### Remediated patch

- visible expired-session test: PASS
- revoked-session counterfactual: PASS
- decision: `SAFE_TO_MERGE`

### Unsupported patch

If the supplied diff cannot be applied to the bounded demo fixture, OMEN does not invent execution evidence. It returns `ASK_CLARIFYING_QUESTION` and preserves the limitation in the trace.

The Python package in the repository remains the core OMEN implementation. The web prototype is the judge-facing executable embodiment of the README's three-plane model.
