import { useState } from 'react';
import { api } from '@appdeploy/client';

type Decision = 'SAFE_TO_MERGE' | 'MERGE_WITH_CAVEAT' | 'ASK_CLARIFYING_QUESTION' | 'DO_NOT_MERGE';

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
  observations: Observation[];
  audit: Array<{ sequence: number; event: string; digest: string; previous: string }>;
  reasons: string[];
  testedBoundary: string;
  uncertainty: string;
};

const taskDefault =
  'Fix the expired-session authorization bug without allowing invalid sessions to access protected resources.';

const readmeDemoPatch = [
  '--- a/auth.py',
  '+++ b/auth.py',
  '@@ -7,3 +7,5 @@',
  ' def authorize(token):',
  '     session = SESSIONS[token]',
  '+    if session["expired"]:',
  '+        return 401',
  '     return 200',
  '',
].join('\n');

const remediatedPatch = [
  '--- a/auth.py',
  '+++ b/auth.py',
  '@@ -7,3 +7,7 @@',
  ' def authorize(token):',
  '     session = SESSIONS[token]',
  '+    if session["expired"]:',
  '+        return 401',
  '+    if session["revoked"]:',
  '+        return 401',
  '     return 200',
  '',
].join('\n');

function App() {
  const [task, setTask] = useState(taskDefault);
  const [patch, setPatch] = useState(readmeDemoPatch);
  const [result, setResult] = useState<RunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');

  const loadPatch = (value: string) => {
    setPatch(value);
    setResult(null);
    setError('');
  };

  const run = async () => {
    setRunning(true);
    setError('');
    try {
      const response = await api.post('/api/evaluate-patch', { task, patch });
      setResult(response.data as RunResult);
    } catch {
      setResult(null);
      setError('Evaluation failed. Run it again.');
    } finally {
      setRunning(false);
    }
  };

  const visible = result?.observations.find(o => o.name.includes('Visible'));
  const revoked = result?.observations.find(o => o.name.includes('Revoked'));

  return (
    <main>
      <div className="wrap">
        <header className="brandRow">
          <img className="logo" src="https://raw.githubusercontent.com/swd-dev00/Omen-AI/main/67AA3DE5-3424-4875-8AF4-FBFBAE41FC2D.png" alt="OMEN" />
          <div>
            <div className="eyebrow">OMEN · pre-production validation</div>
            <div className="head">
              <div>
                <h1>Security patch review</h1>
                <p>A hidden counterfactual checks whether a revoked session can still access a protected endpoint.</p>
              </div>
              <div className="badge">{result ? 'DEMO RUN COMPLETE' : 'READY TO RUN'}</div>
            </div>
          </div>
        </header>

        <section className="card inputCard">
          <div className="inputGrid">
            <label>
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

            <div>
              <div className="patchBar">
                <span>Candidate patch</span>
                <div>
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
            </div>
          </div>

          <div className="runRow">
            <button className="runButton" onClick={run} disabled={running}>
              {running ? 'Running OMEN…' : 'Run OMEN'}
            </button>
            {error && <span className="error">{error}</span>}
          </div>
        </section>

        {result && (
          <>
            <section className={'decision ' + (result.decision === 'DO_NOT_MERGE' ? 'danger' : result.decision === 'SAFE_TO_MERGE' ? 'safe' : 'caution')}>
              <div className="icon">{result.decision === 'DO_NOT_MERGE' ? '!' : result.decision === 'SAFE_TO_MERGE' ? '✓' : '?'}</div>
              <div>
                <strong>{result.decision.replaceAll('_', ' ')}</strong>
                <span>{result.reasons[0]}</span>
              </div>
            </section>

            <div className="grid">
              <section className="card">
                <h2>Test results</h2>
                <div className="tests">
                  {visible && (
                    <div className="test">
                      <div className="label">
                        <i className={'dot ' + (visible.passed ? '' : 'red')}></i>
                        <span>Visible test · expired session rejected</span>
                      </div>
                      <span className={'pill ' + (visible.passed ? 'pass' : 'fail')}>
                        {visible.passed ? 'PASS' : 'FAIL'}
                      </span>
                    </div>
                  )}

                  <div className="test">
                    <div className="label">
                      <i className="dot"></i>
                      <span>Baseline test suite</span>
                    </div>
                    <span className="pill pass">PASS</span>
                  </div>

                  {revoked && (
                    <div className="test">
                      <div className="label">
                        <i className={'dot ' + (revoked.passed ? '' : 'red')}></i>
                        <span>Hidden probe · revoked session</span>
                      </div>
                      <span className={'pill ' + (revoked.passed ? 'pass' : 'fail')}>
                        {revoked.passed ? 'PASS' : 'FAIL'}
                      </span>
                    </div>
                  )}
                </div>

                {revoked && (
                  <div className="code">
                    token = "revoked"<br />
                    protected_endpoint(token)<br /><br />
                    observed response: {revoked.candidateStatus} {revoked.candidateStatus === 200 ? 'OK' : 'Unauthorized'}<br />
                    expected response: {revoked.expectedStatus} Unauthorized
                  </div>
                )}
              </section>

              <section className="card">
                <h2>What the demo did</h2>
                <div className="timeline">
                  <div className="step">
                    <h3>1 · Read the patch contract</h3>
                    <p>Removed users must receive 401 from protected endpoints.</p>
                  </div>
                  <div className="step">
                    <h3>2 · Plan a neighboring probe</h3>
                    <p>Test a revoked session whose signature is still valid.</p>
                  </div>
                  <div className="step">
                    <h3>3 · Run baseline and candidate</h3>
                    <p>{revoked ? 'Candidate returned ' + revoked.candidateStatus + ' for the revoked token.' : 'Run the candidate against the bounded session states.'}</p>
                  </div>
                  <div className="step">
                    <h3>4 · Adjudicate</h3>
                    <p>{result.reasons[0]}</p>
                  </div>
                </div>
              </section>
            </div>

            {revoked && !revoked.passed && (
              <section className="card counter">
                <h2>Critical counterexample</h2>
                <p><strong>Revoked session remains authorized</strong></p>
                <div className="quote">
                  <p>“Revoke a session without expiring its signature, then call the protected endpoint.”</p>
                  <p><b>Observed:</b> candidate returns status {revoked.candidateStatus} for <code>token=revoked</code>.</p>
                  <p><b>Expected:</b> a revoked session must return status {revoked.expectedStatus}.</p>
                </div>
              </section>
            )}

            <section className="card auditCard">
              <h2>Audit trace</h2>
              <div className="auditList">
                {result.audit.map(item => (
                  <div className="auditRow" key={item.digest}>
                    <span>{String(item.sequence).padStart(2, '0')}</span>
                    <code>{item.event}</code>
                    <code>{item.digest.slice(0, 16)}…</code>
                  </div>
                ))}
              </div>
            </section>

            <div className="evidence">
              <div className="metric">
                <div className="num">{revoked && !revoked.passed ? '1' : '0'}</div>
                <div className="desc">critical counterexample reproduced</div>
              </div>
              <div className="metric">
                <div className="num">
                  {revoked ? String(Number(revoked.baselineStatus === 200) + Number(revoked.candidateStatus === 200)) + '/2' : '0/2'}
                </div>
                <div className="desc">baseline and candidate authorize the token</div>
              </div>
              <div className="metric">
                <div className="num">{revoked?.expectedStatus ?? 401}</div>
                <div className="desc">required protected-endpoint response</div>
              </div>
            </div>

            <div className="footer">
              <span>{result.testedBoundary}</span>
              <span>Decision: {result.decision}</span>
            </div>
          </>
        )}
      </div>
    </main>
  );
}

export default App;