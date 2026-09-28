##Omen-AI

OMEN is the liability gate between an AI decision and the real-world action it can trigger.\n\n## Working prototype\n\n**Live:** https://omen-hmgqez.v2.appdeploy.ai/\n\nThe live prototype is executable. A judge changes the candidate authorization guards and OMEN's backend runs the baseline, visible expired-session test, and revoked-session counterfactual itself. The resulting observations are committed into a SHA-256 hash-linked audit trace before the Policy Plane issues `DO_NOT_MERGE` or `SAFE_TO_MERGE`. The deployed source is checked into `web-prototype/`.

OMEN started from a problem I kept running into while working on AI governance: we are giving AI systems more authority to act, but most of the accountability still begins after something goes wrong. We review logs, investigate incidents, reconstruct decisions, and then try to figure out who approved the action, what evidence existed, which policy applied, and whether the system should have been allowed to act in the first place. I wanted to move that entire conversation closer to the point of execution.

The central question behind OMEN is simple: before an AI-driven action is allowed to proceed, what should the system have to prove? I am not interested in treating model confidence, a polished explanation, or a successful test as enough on its own. I want the system to be able to show what was requested, what was executed, what evidence was produced, what policy governed the action, what uncertainty remained, and why the final decision was allowed or blocked.

The current working prototype applies that idea to AI-assisted software development because it gives me a place where the oversight model can be tested against something concrete. In the demo, OMEN can stop a change even when the visible test suite passes, because it looks beyond the test the developer expected and checks whether a nearby failure state is still present.

##Why I built OMEN

AI systems are already being used to modify software, trigger workflows, call tools, interact with infrastructure, make recommendations, and influence decisions that have real downstream consequences. The problem is that a lot of governance still assumes the system will act first and be reviewed later. That is useful for investigation, but it does not do much to stop a bad action before it happens.

I wanted OMEN to sit closer to that boundary. Instead of asking only whether an AI output looks reasonable, the system asks whether enough evidence exists to justify letting the action continue. That changes the role of oversight from something that documents behavior afterward into something that can participate in the decision before execution.

This is also why OMEN is broader than the software demo. The patch workflow is one implementation of the larger idea. The real project is about AI liability oversight, especially in environments where an automated decision can move from analysis into action and someone later needs to be able to explain exactly why that action was permitted.

##What OMEN does

OMEN separates three responsibilities that I do not think should live in the same layer: execution, evidence preservation, and policy. That separation became the basis of the three-plane architecture.

Execution Plane -> Audit Plane -> Policy Plane

The Execution Plane is responsible for establishing what actually happened. In the current prototype, that includes baseline behavior, candidate behavior, visible tests, counterfactual probes, and bounded reproductions. Its job is to execute and observe. It does not decide whether the result is safe, acceptable, compliant, or allowed.

The Audit Plane preserves the evidence created by execution. That includes inputs, outputs, execution conditions, baseline observations, candidate observations, counterfactual results, timestamps, policy references, hashes, and decision records. The point is to make sure later policy decisions cannot quietly rewrite the facts that produced them.

The Policy Plane evaluates the preserved evidence and determines what the system is allowed to do next. In the current software prototype, that can result in outcomes such as:

SAFE_TO_MERGE
MERGE_WITH_CAVEAT
ASK_CLARIFYING_QUESTION
DO_NOT_MERGE

The model does not get final authority over those outcomes. A model can suggest that something should be tested, identify a possible obligation, or point out a condition that deserves more attention, but that suggestion is not treated as proof. OMEN has to run the relevant check, observe the behavior, preserve the evidence, and then apply the active policy to that evidence.

That separation is one of the most important parts of the project because I do not want a system that executes an action, judges its own behavior, and then creates the record used to justify the result.

The working demo

The current demo uses an authorization bug because it gives OMEN a clear and falsifiable way to show whether the oversight model is doing anything useful.

The candidate patch is supposed to fix an expired-session problem, and it does. The visible test passes. In a normal development workflow, that might be treated as enough evidence to move forward.

OMEN continues by asking whether another closely related invalid state was handled correctly. It tests what happens when a session has been revoked but has not yet expired. That case was not covered by the original acceptance test, and the revoked session is still authorized.

So the system now has two observations:

Visible expired-session test: PASS
Revoked-session counterfactual: FAIL

The patch fixed the condition it was explicitly asked to fix, but the broader security obligation is still broken. OMEN records the counterexample, preserves the evidence, and returns:

DO_NOT_MERGE

The important part is not the phrase DO_NOT_MERGE. The important part is that OMEN can show why it reached that decision. It can show what was tested, what was expected, what actually happened, which policy rule applied, and what evidence made the change ineligible to proceed.

##How I built it

OMEN is currently written in Python and uses pytest for deterministic test execution. The prototype creates separate baseline and candidate execution contexts, applies the candidate patch, runs the declared test suite, and then evaluates bounded counterfactual conditions around the requested behavior. The strengthened build currently passes 19 out of 19 tests.

I also added support for model-assisted analysis through OpenAI-compatible APIs and an NVIDIA Nemotron integration path. The model can help identify obligations, suggest counterfactual states, interpret repository context, propose additional tests, and explain findings, but I deliberately kept it out of the final authority path.

That was an important design choice. I did not want OMEN to become a system where the model generates the reasoning, grades its own reasoning, and then produces the evidence used to justify the decision. If the model suggests that a revoked session may be a problem, OMEN still has to execute that condition and observe what happens. If the model says a failure looks serious, the Policy Plane still needs an explicit rule that maps the reproduced evidence to a blocking or non-blocking outcome.

The system also uses isolated baseline and candidate working copies, bounded runtime controls, POSIX resource limits, and capability-checked Linux network namespaces when the host supports them. I would rather expose the limits of the execution environment than imply that the prototype has stronger isolation than it actually does.

Decision model

OMEN treats the governance decision as a function of observed evidence and an explicit policy version:

$$
D = f(O, P_v)
$$

where (D) is the final decision, (O) is the set of observed evidence, and (P_v) is the active policy version.

A reproduced critical counterexample can force a blocking outcome:

$$
C_{\text{critical}} = 1
\Rightarrow
D = \text{DO_NOT_MERGE}
$$

The broader principle behind that rule is simple: the strength of the decision should never exceed the strength of the evidence supporting it.

That principle also affects how OMEN handles incomplete information. If the system does not have enough comparative evidence to support a strong conclusion, it should preserve that uncertainty instead of manufacturing confidence.

Counterfactual testing

One of the biggest things I learned while building OMEN is that a passing test suite only tells you that the tests you ran passed. It does not prove that every relevant state around that behavior is safe.

If (T) is the set of tests that were executed, then:

$$
\forall t \in T,\quad t = \text{PASS}
$$

does not prove:

$$
\forall s \in S,\quad s = \text{SAFE}
$$

where (S) represents every relevant state the system could enter.

That gap is where counterfactual testing became important. OMEN does not try to enumerate every possible failure state, because that would not be realistic. Instead, it looks for bounded neighboring conditions that are close enough to the original obligation to matter.

In the demo, the visible requirement tests session expiration. The counterfactual asks whether another invalid state, revocation, is handled correctly too. That is how OMEN finds a failure the original test suite missed without pretending it has proven universal safety.

Current-state safeguards

Another issue I caught during development involved current-state inspection. If OMEN inspects the current system without evaluating an actual candidate change, it does not have enough comparative evidence to claim that something is safe to merge.

That sounds obvious when stated plainly, but it is exactly the kind of overclaiming that automated systems can make if the decision logic is not careful. I changed the policy behavior so a current-state inspection cannot return an unconditional SAFE_TO_MERGE.

If the evidence is incomplete, OMEN has to preserve that limitation. I would rather have the system say that it does not have enough evidence than produce a cleaner answer that it cannot support.

Current capabilities

The strengthened prototype currently includes deterministic baseline and candidate execution, Git patch application, visible test execution, bounded counterfactual probes, failure reproduction, fail-closed policy behavior, explicit policy overrides, current-state safeguards, uncertainty reporting, a working CLI, a repeatable demo, isolated temporary working copies, POSIX resource limits, capability-checked Linux network namespaces, OpenAI-compatible model integration, an NVIDIA Nemotron integration path, and 19 passing tests.

>> Running OMEN

OMEN currently requires Python 3.10 or newer and Git.

Create a virtual environment: python3 -m venv .venv

Activate it: source .venv/bin/activate

Install OMEN and the development dependencies: pip install -e '.[dev]'

Run the test suite: python3 -m pytest -q

Expected result: 19 passed

Run the deterministic demo: PYTHONPATH=. python3 demo/run_demo.py

The demo does not require external model credentials. The expected governance decision is: DO_NOT_MERGE

Repository structure

omen/
    engine.py
    models.py
    policy.py
    ...
demo/
    run_demo.py
tests/
    test_omen.py
    ...
README.md
LEXHACK_SUBMISSION.md
DEMO_SCRIPT.md
DEMO_OUTPUT.txt

The internal structure will continue changing as I finish separating the Execution, Audit, and Policy planes and formalize the interfaces between them.

##Where the architecture is going

The next major step is finishing the de-hybridization of the architecture so that Execution, Audit, and Policy communicate through explicit artifacts instead of reaching into each other’s internal state.

That means formalizing objects such as:

ExecutionIntent
ExecutionSpec
ObservationSet
CounterfactualProbe
AuditRecord
PolicyDecision
IntegrityReceipt

I also want the Audit Plane to use an append-only hash chain so each record commits to the one before it.

For records (R_0, R_1, …, R_n):

$$
H_i =
\operatorname{SHA256}(R_i \parallel H_{i-1})
$$

If an earlier record is changed later, the downstream chain no longer verifies. That gives OMEN trace integrity without adding blockchain infrastructure or pretending unrelated executions need global consensus.

The larger goal is to make it possible to inspect the entire path from request to execution to evidence to policy decision without coupling those responsibilities together.

##What OMEN is not

OMEN is still a research and engineering prototype. It does not claim to prove universal software safety, eliminate AI liability, replace legal review, establish that an organization has lawful authority, provide perfect sandbox isolation on every host, or enumerate every possible failure state.

The goal is narrower and more useful than that. OMEN is trying to make execution, evidence, policy, uncertainty, and responsibility easier to separate, inspect, and defend.

##What comes next

The software demo is the first environment where I can test the architecture rigorously, but it is not the boundary of the project. The larger direction is AI liability oversight across consequential systems where an AI decision can trigger an action and someone may later need to explain exactly why that action was allowed.

I want OMEN to be able to answer, with evidence, what was requested, who or what initiated it, what authority applied, what actually happened during execution, what evidence existed, which policy governed the decision, what uncertainty remained, and why the system allowed or blocked the action.

That is the boundary I am building around.

LexHack 2026

OMEN was developed as a working prototype for LexHack 2026.

Elevator pitch

OMEN is the liability gate between an AI decision and the real-world action it can trigger.

Built with

Python, pytest, Git, SHA-256, deterministic policy gates, counterfactual testing, OpenAI-compatible APIs, NVIDIA Nemotron, Linux process isolation, POSIX resource limits, and isolated baseline and candidate worktrees.

License

Copyright © 2026 Sierra Warren. All rights reserved.

OMEN and its associated source code, architecture, documentation, designs, and materials are proprietary works. This repository is publicly viewable for evaluation, demonstration, research review, and hackathon judging.

No permission is granted to copy, modify, distribute, sublicense, sell, commercialize, incorporate OMEN into another product, or create derivative works without prior written permission. Third-party libraries and dependencies remain subject to their own licenses.

See LICENSE for additional terms.
