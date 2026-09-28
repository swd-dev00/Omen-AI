import { useState } from 'react';
import { api } from '@appdeploy/client';
import { Check, X, RotateCcw } from 'lucide-react';

type Decision =
  | 'SAFE_TO_MERGE'
  | 'MERGE_WITH_CAVEAT'
  | 'ASK_CLARIFYING_QUESTION'
  | 'DO_NOT_MERGE';

type Observation = {
  name: string;
  baselineStatus: number;
  candidateStatus: number;
  expectedStatus: number;
  passed: boolean;
};

type RunResult = {
  traceId: string;
  patchStatus: 'applied' | 'rejected';
  decision: Decision;
  baselineSource: string;
  candidateSource: string;
  observations: Observation[];
  audit: Array<{
    sequence: number;
    event: string;
    digest: string;
    previous: string;
  }>;
  reasons: string[];
  testedBoundary: string;
  uncertainty: string;
};

const taskDefault =
  'Fix the expired-session authorization bug without allowing invalid sessions to access protected resources.';

const readmeDemoPatch = `--- a/auth.py
+++ b/auth.py
@@ -7,3 +7,5 @@
 def authorize(token):
     session = SESSIONS[token]
+    if session["expired"]:
+        return 401
     return 200
`;

const remediatedPatch = `--- a/auth.py
+++ b/auth.py
@@ -7,3 +7,7 @@
 def authorize(token):
     session = SESSIONS[token]
+    if session["expired"]:
+        return 401
+    if session["revoked"]:
+        return 401
     return 200
`;

function App() {
  const [task, setTask] = useState(taskDefault);
  const [patch, setPatch] = useState(readmeDemoPatch);
  const [result, setResult] = useState<RunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState('');

  const loadPatch = (value: string) => {
    setPatch(value);
    setResult(null);
    setMessage('');
  };

  const run = async () => {
    setRunning(true);
    setMessage('');
    try {
      const response = await api.post('/api/evaluate-patch', { task, patch });
      setResult(response.data as RunResult);
    } catch {
      setResult(null);
      setMessage('The evaluation did not complete. Run it again.');
    } finally {
      setRunning(false);
    }
  };

  const blocked = result?.decision === 'DO_NOT_MERGE';
  const allowed = result?.decision === 'SAFE_TO_MERGE';

  return (
    <main className="page">
      <header className="topbar">
        <div className="brand">
          <strong>OMEN</strong>
          <span>the liability gate between an AI decision and the real-world action it can trigger</span>
        </div>
        <a href="https://github.com/swd-dev00/Omen-AI" target="_blank" rel="noreferrer">
          swd-dev00 / Omen-AI
        </a>
      </header>

      <section className="intro">
        <p className="eyebrow">AI-ASSISTED SOFTWARE DEVELOPMENT PROTOTYPE</p>
        <h1>What should the system have to prove before the action proceeds?</h1>
        <p>
          OMEN separates execution, evidence preservation, and policy. The candidate patch is evaluated
          against the visible requirement and a bounded neighboring failure state before the Policy Plane
          is allowed to issue a merge decision.
        </p>
      </section>

      <section className="workspace">
        <section className="panel inputPanel">
          <div className="panelTitle">
            <span>REQUEST</span>
            <h2>Candidate change</h2>
          </div>

          <label className="field">
            <span>Task contract</span>
            <textarea
              className="task"
              value={task}
              onChange={e => {
                setTask(e.target.value);
                setResult(null);
              }}
            />
          </label>

          <div className="patchHeader">
            <div>
              <span>PROPOSED UNIFIED DIFF</span>
              <small>Built-in demo repository: auth.py</small>
            </div>
            <div className="quick">
              <button onClick={() => loadPatch(readmeDemoPatch)}>README demo patch</button>
              <button onClick={() => loadPatch(remediatedPatch)}>Remediated patch</button>
            </div>
          </div>

          <textarea
            className="patchEditor"
            spellCheck={false}
            value={patch}
            onChange={e => {
              setPatch(e.target.value);
              setResult(null);
            }}
          />

          <button className="run" onClick={run} disabled={running}>
            {running ? 'Executing OMEN evaluation…' : 'Run OMEN'}
          </button>
          <button className="reset" onClick={() => loadPatch(readmeDemoPatch)}>
            <RotateCcw size={14} /> Reset README demo
          </button>
          {message && <p className="error">{message}</p>}
        </section>

        <section className="panel outputPanel">
          <div className="panelTitle">
            <span>EVIDENCE</span>
            <h2>Request → execution → evidence → policy</h2>
          </div>

          {!result ? (
            <div className="empty">
              <strong>No evaluation yet.</strong>
              <span>Run the candidate patch. OMEN will establish the observations, preserve them, then apply policy.</span>
            </div>
          ) : (
            <>
              <section className="plane">
                <div className="planeHeading">
                  <span>EXECUTION PLANE</span>
                  <small>Establishes what actually happened. It cannot authorize the merge.</small>
                </div>

                <div className="patchStatus">
                  <span>candidate patch</span>
                  <strong>{result.patchStatus.toUpperCase()}</strong>
                </div>

                {result.observations.map(observation => (
                  <div className="observation" key={observation.name}>
                    <div className="obsHead">
                      <strong>{observation.name}</strong>
                      <span className={observation.passed ? 'pass' : 'fail'}>
                        {observation.passed ? <Check size={14} /> : <X size={14} />}
                        {observation.passed ? 'PASS' : 'FAIL'}
                      </span>
                    </div>
                    <div className="matrix">
                      <span>baseline <b>{observation.baselineStatus}</b></span>
                      <span>candidate <b>{observation.candidateStatus}</b></span>
                      <span>expected <b>{observation.expectedStatus}</b></span>
                    </div>
                  </div>
                ))}
              </section>

              <section className="plane">
                <div className="planeHeading">
                  <span>AUDIT PLANE</span>
                  <small>Preserves the evidence in an append-only SHA-256 hash chain.</small>
                </div>
                <div className="audit">
                  {result.audit.map(item => (
                    <div className="auditRow" key={item.digest}>
                      <small>{String(item.sequence).padStart(2, '0')}</small>
                      <code>{item.event}</code>
                      <code>{item.digest.slice(0, 12)}…</code>
                    </div>
                  ))}
                </div>
              </section>

              <section className="plane policyPlane">
                <div className="planeHeading">
                  <span>POLICY PLANE</span>
                  <small>Evaluates preserved evidence and owns the final merge decision.</small>
                </div>

                <div className={blocked ? 'verdict blocked' : allowed ? 'verdict allowed' : 'verdict caveat'}>
                  <span>POLICY DECISION</span>
                  <strong>{result.decision}</strong>
                  <small>trace {result.traceId.slice(0, 18)}</small>
                </div>

                <div className="reasons">
                  {result.reasons.map(reason => <p key={reason}>{reason}</p>)}
                </div>
              </section>

              <section className="boundary">
                <div><span>TESTED BOUNDARY</span><p>{result.testedBoundary}</p></div>
                <div><span>UNCERTAINTY</span><p>{result.uncertainty}</p></div>
              </section>
            </>
          )}
        </section>
      </section>

      <footer>
        <span>Execution tells us what happened.</span>
        <span>Audit preserves what happened.</span>
        <span>Policy decides what is allowed.</span>
      </footer>
    </main>
  );
}

export default App;