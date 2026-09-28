# 2–3 Minute Demo Script

1. **Problem (20 sec)**
   AI coding agents can make a patch look safe because the visible tests pass, even when an important neighboring state is still broken. OMEN asks what the patch failed to prove before it is merged.

2. **Run the demo (20 sec)**
   Run `PYTHONPATH=. python3 demo/run_demo.py`. The candidate patch fixes the visible expired-session test.

3. **Show the trap (35 sec)**
   The visible test passes, but OMEN separately probes a revoked-but-unexpired session. That state still receives authorization. The flaw existed in the baseline and survives the candidate patch.

4. **Show the decision (30 sec)**
   OMEN returns `DO_NOT_MERGE`, identifies the reproduced critical counterexample, records the observed versus expected behavior, and recommends the next remediation step.

5. **Explain the governance model (35 sec)**
   The model is not the final authority. Deterministic policy rules override it when a critical failure reproduces, an explicit obligation lacks evidence, a probe fails, or sandbox integrity is compromised.

6. **Close (20 sec)**
   OMEN turns pre-merge review from “the tests are green” into “the system has evidence for the states that matter, and it can show exactly what remains unsafe.”
