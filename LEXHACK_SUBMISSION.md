# OMEN — LexHack 2026 Submission Notes

## Short summary
OMEN is a fail-closed pre-merge safety gate for AI-assisted software. It pressure-tests a candidate patch against explicit task obligations and counterfactual failure states before allowing a merge recommendation.

## Problem
AI coding tools are often evaluated against the visible tests in a repository. A patch can satisfy those tests while leaving a nearby safety state broken, especially when the failure is pre-existing or absent from the original acceptance suite. In high-impact software, a green test suite is not enough evidence that a change is safe to merge.

## Solution
OMEN reconstructs the task contract, runs the baseline and candidate test suites, executes bounded counterfactual probes through a narrow repository adapter, and sends the resulting evidence through a deterministic fail-closed policy gate. The model may analyze and recommend, but it cannot override reproduced critical failures, missing obligations, failed probes, or sandbox-integrity violations.

## Demo payoff
The included deterministic demo evaluates a patch intended to prevent removed users from accessing protected resources. The candidate fixes an expired-session case and passes the visible test. OMEN then tests the neighboring revoked-session state, reproduces a critical authorization failure, and returns `DO_NOT_MERGE`.

## Decisions
- SAFE_TO_MERGE
- MERGE_WITH_CAVEAT
- ASK_CLARIFYING_QUESTION
- DO_NOT_MERGE

## Built with
Python 3.10+, pytest, OpenAI-compatible model APIs, NVIDIA Nemotron integration path, Git patch application, deterministic policy logic, isolated temporary baseline/candidate copies, resource limits, and capability-checked Linux network namespaces when supported.

## Safety boundary
OMEN is a hackathon prototype and does not claim perfect isolation or universal software safety. Its reports explicitly state the tested boundary and whether stronger runtime controls were actually available on the host.


## Live prototype
https://omen-hmgqez.v2.appdeploy.ai/

The hosted prototype accepts a task contract and proposed unified diff against the built-in authorization fixture. OMEN applies the recognized patch, computes baseline and candidate behavior, executes the visible expired-session test and revoked-but-unexpired counterfactual, preserves the resulting evidence in a SHA-256 hash-linked audit trace, and then applies the deterministic Policy Plane. Unsupported patches return `ASK_CLARIFYING_QUESTION` rather than fabricated evidence.
