import { useState } from 'react';
import { api } from '@appdeploy/client';
import { Check, X, RotateCcw } from 'lucide-react';

type RunResult = {
  traceId: string;
  decision: 'SAFE_TO_MERGE' | 'DO_NOT_MERGE';
  candidateSource: string;
  observations: Array<{
    name: string;
    baselineStatus: number;
    candidateStatus: number;
    expectedStatus: number;
    passed: boolean;
  }>;
  audit: Array<{
    sequence: number;
    event: string;
    digest: string;
    previous: string;
  }>;
  reasons: string[];
};

type Candidate = {
  denyExpired: boolean;
  denyRevoked: boolean;
  requireValidSignature: boolean;
};

const defaultCandidate: Candidate = {
  denyExpired: true,
  denyRevoked: false,
  requireValidSignature: true,
};

function App() {
  const [candidate, setCandidate] = useState<Candidate>(defaultCandidate);
  const [result, setResult] = useState<RunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState('');

  const setRule = (key: keyof Candidate, value: boolean) => {
    setCandidate(current => ({ ...current, [key]: value }));
    setResult(null);
    setMessage('');
  };

  const loadVulnerable = () => {
    setCandidate(defaultCandidate);
    setResult(null);
    setMessage('');
  };

  const loadRemediated = () => {
    setCandidate({ denyExpired: true, denyRevoked: true, requireValidSignature: true });
    setResult(null);
    setMessage('');
  };

  const run = async () => {
    setRunning(true);
    setMessage('');
    try {
      const response = await api.post('/api/run', { candidate });
      setResult(response.data as RunResult);
    } catch {
      setMessage('The evaluation did not complete. Run it again.');
    } finally {
      setRunning(false);
    }
  };

  const sourceLines = [
    'function authorize(session) {',
    candidate.requireValidSignature ? '  if (!session.signatureValid) return 401;' : '',
    candidate.denyExpired ? '  if (session.expired) return 401;' : '',
    candidate.denyRevoked ? '  if (session.revoked) return 401;' : '',
    '  return 200;',
    '}',
  ].filter(Boolean);

  return (
    <main className="page">
      <header className="topbar">
        <div className="brand"><strong>OMEN</strong><span>pre-merge computational assurance</span></div>
        <a href="https://github.com/swd-dev00/Omen-AI" target="_blank" rel="noreferrer">swd-dev00 / Omen-AI</a>
      </header>

      <section className="intro">
        <p className="eyebrow">WORKING PROTOTYPE</p>
        <h1>Give OMEN a candidate. Let OMEN produce the evidence.</h1>
        <p>
          Change the authorization patch below. The backend executes the baseline and candidate against
          the visible requirement and a revoked-session counterfactual. You do not enter the test result.
        </p>
      </section>

      <section className="workspace">
        <section className="panel">
          <div className="panelTitle"><span>CANDIDATE PATCH</span><h2>Authorization guards</h2></div>

          <div className="ruleList">
            <label>
              <input type="checkbox" checked={candidate.requireValidSignature} onChange={e => setRule('requireValidSignature', e.target.checked)} />
              <span><strong>Require valid signature</strong><small>Reject an invalid token signature.</small></span>
            </label>
            <label>
              <input type="checkbox" checked={candidate.denyExpired} onChange={e => setRule('denyExpired', e.target.checked)} />
              <span><strong>Deny expired sessions</strong><small>This is the visible acceptance requirement.</small></span>
            </label>
            <label>
              <input type="checkbox" checked={candidate.denyRevoked} onChange={e => setRule('denyRevoked', e.target.checked)} />
              <span><strong>Deny revoked sessions</strong><small>This is the neighboring counterfactual state.</small></span>
            </label>
          </div>

          <div className="quick">
            <button onClick={loadVulnerable}>Load visible-test-only patch</button>
            <button onClick={loadRemediated}>Load remediated patch</button>
          </div>

          <div className="source">
            <div>candidate/auth.ts</div>
            <pre>{sourceLines.join('\n')}</pre>
          </div>

          <button className="run" onClick={run} disabled={running}>
            {running ? 'Running execution + audit + policy…' : 'Run OMEN'}
          </button>
          <button className="reset" onClick={loadVulnerable}><RotateCcw size={14}/> Reset</button>
          {message && <p className="error">{message}</p>}
        </section>

        <section className="panel results">
          <div className="panelTitle"><span>OMEN OUTPUT</span><h2>Observed evidence</h2></div>

          {!result ? (
            <div className="empty">
              <strong>Nothing has been evaluated yet.</strong>
              <span>Run OMEN. The backend will execute the test cases and populate this side.</span>
            </div>
          ) : (
            <>
              <div className={result.decision === 'DO_NOT_MERGE' ? 'verdict blocked' : 'verdict allowed'}>
                <span>POLICY DECISION</span>
                <strong>{result.decision}</strong>
                <small>trace {result.traceId.slice(0, 16)}</small>
              </div>

              <div className="observations">
                {result.observations.map(o => (
                  <div className="observation" key={o.name}>
                    <div className="obsHead">
                      <strong>{o.name}</strong>
                      <span className={o.passed ? 'pass' : 'fail'}>{o.passed ? <Check size={14}/> : <X size={14}/>} {o.passed ? 'PASS' : 'FAIL'}</span>
                    </div>
                    <div className="matrix">
                      <span>baseline <b>{o.baselineStatus}</b></span>
                      <span>candidate <b>{o.candidateStatus}</b></span>
                      <span>expected <b>{o.expectedStatus}</b></span>
                    </div>
                  </div>
                ))}
              </div>

              <div className="reason">
                <span>POLICY BASIS</span>
                {result.reasons.map(reason => <p key={reason}>{reason}</p>)}
              </div>

              <div className="audit">
                <div className="auditLabel">HASH-LINKED AUDIT TRACE</div>
                {result.audit.map(item => (
                  <div className="auditRow" key={item.digest}>
                    <small>{String(item.sequence).padStart(2, '0')}</small>
                    <code>{item.event}</code>
                    <code>{item.digest.slice(0, 11)}…</code>
                  </div>
                ))}
              </div>
            </>
          )}
        </section>
      </section>

      <footer>
        <span>Execution runs the cases.</span>
        <span>Audit preserves the observations.</span>
        <span>Policy owns the verdict.</span>
      </footer>
    </main>
  );
}

export default App;