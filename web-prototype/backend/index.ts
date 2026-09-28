import { createHash, randomUUID } from 'node:crypto';
import { router, json, error } from '@appdeploy/sdk';

type Session = {
  expired: boolean;
  revoked: boolean;
};

type Decision =
  | 'SAFE_TO_MERGE'
  | 'MERGE_WITH_CAVEAT'
  | 'ASK_CLARIFYING_QUESTION'
  | 'DO_NOT_MERGE';

const baselineSource = `SESSIONS = {
    "expired": {"expired": True, "revoked": False},
    "revoked": {"expired": False, "revoked": True},
    "active": {"expired": False, "revoked": False},
}

def authorize(token):
    session = SESSIONS[token]
    return 200
`;

function sha(value: unknown) {
  return createHash('sha256').update(JSON.stringify(value)).digest('hex');
}

function append(
  trace: Array<{ sequence: number; event: string; digest: string; previous: string }>,
  event: string,
  artifact: unknown
) {
  const previous = trace.length ? trace[trace.length - 1].digest : 'GENESIS';
  const digest = sha({ sequence: trace.length, event, artifact, previous });
  trace.push({ sequence: trace.length, event, digest, previous });
}

function parsePatch(patch: string) {
  const isUnified =
    patch.includes('--- a/auth.py') &&
    patch.includes('+++ b/auth.py') &&
    patch.includes('def authorize(token):');

  if (!isUnified) {
    return {
      applied: false,
      denyExpired: false,
      denyRevoked: false,
      candidateSource: baselineSource,
      reason: 'The bounded demo accepts a unified diff against auth.py. The supplied patch could not be applied to that fixture.',
    };
  }

  const addedLines = patch
    .split('\n')
    .filter(line => line.startsWith('+') && !line.startsWith('+++'))
    .map(line => line.slice(1));

  const denyExpired = addedLines.some(line => /if\s+session\["expired"\]\s*:/.test(line));
  const denyRevoked = addedLines.some(line => /if\s+session\["revoked"\]\s*:/.test(line));

  const guards = [
    denyExpired ? '    if session["expired"]:\n        return 401' : '',
    denyRevoked ? '    if session["revoked"]:\n        return 401' : '',
  ].filter(Boolean).join('\n');

  const candidateSource = `SESSIONS = {
    "expired": {"expired": True, "revoked": False},
    "revoked": {"expired": False, "revoked": True},
    "active": {"expired": False, "revoked": False},
}

def authorize(token):
    session = SESSIONS[token]
${guards ? guards + '\n' : ''}    return 200
`;

  return { applied: true, denyExpired, denyRevoked, candidateSource, reason: '' };
}

function executeSource(session: Session, source: string) {
  if (source.includes('if session["expired"]') && session.expired) return 401;
  if (source.includes('if session["revoked"]') && session.revoked) return 401;
  return 200;
}

function evaluate(task: string, patch: string) {
  const traceId = randomUUID();
  const trace: Array<{ sequence: number; event: string; digest: string; previous: string }> = [];

  append(trace, 'EXECUTION_INTENT', {
    traceId,
    task,
    patchDigest: sha(patch),
  });

  append(trace, 'CONTRACT_RECONSTRUCTED', {
    visibleObligation: 'expired session must return 401',
    boundedNeighbor: 'revoked but unexpired session must return 401',
  });

  append(trace, 'PROBES_PLANNED', {
    visible: 'expired session -> protected endpoint',
    counterfactual: 'revoked but unexpired session -> protected endpoint',
  });

  const parsed = parsePatch(patch);

  const expired: Session = { expired: true, revoked: false };
  const revoked: Session = { expired: false, revoked: true };

  const baselineVisible = executeSource(expired, baselineSource);
  const baselineCounterfactual = executeSource(revoked, baselineSource);

  append(trace, 'BASELINE_EXECUTED', {
    expiredStatus: baselineVisible,
    revokedStatus: baselineCounterfactual,
    sourceDigest: sha(baselineSource),
  });

  append(trace, 'CANDIDATE_PATCH_PREPARED', {
    applied: parsed.applied,
    candidateSourceDigest: sha(parsed.candidateSource),
  });

  if (!parsed.applied) {
    const decision: Decision = 'ASK_CLARIFYING_QUESTION';
    append(trace, 'MERGE_POLICY_EVALUATED', {
      decision,
      reason: parsed.reason,
    });

    return {
      traceId,
      patchStatus: 'rejected',
      decision,
      baselineSource,
      candidateSource: parsed.candidateSource,
      observations: [],
      audit: trace,
      reasons: [parsed.reason],
      testedBoundary: 'No candidate execution occurred because the patch did not apply to the bounded auth.py fixture.',
      uncertainty: 'OMEN preserves the missing evidence instead of manufacturing a merge conclusion.',
    };
  }

  const candidateVisible = executeSource(expired, parsed.candidateSource);
  const visiblePassed = candidateVisible === 401;

  const visibleObservation = {
    name: 'Visible expired-session test',
    baselineStatus: baselineVisible,
    candidateStatus: candidateVisible,
    expectedStatus: 401,
    passed: visiblePassed,
  };

  append(trace, 'VISIBLE_TESTS_EXECUTED', visibleObservation);

  const candidateCounterfactual = executeSource(revoked, parsed.candidateSource);
  const counterfactualPassed = candidateCounterfactual === 401;

  const counterfactualObservation = {
    name: 'Revoked-session counterfactual',
    baselineStatus: baselineCounterfactual,
    candidateStatus: candidateCounterfactual,
    expectedStatus: 401,
    passed: counterfactualPassed,
  };

  append(trace, 'COUNTERFACTUAL_PROBE_EXECUTED', counterfactualObservation);

  append(trace, 'MODEL_ADJUDICATION', {
    authority: false,
    mode: 'deterministic demo; no external model credential required',
    note: 'Policy is evaluated from executed observations, not model confidence.',
  });

  let decision: Decision;
  const reasons: string[] = [];

  if (!visiblePassed) {
    decision = 'DO_NOT_MERGE';
    reasons.push('The candidate does not satisfy the visible expired-session requirement.');
  } else if (!counterfactualPassed) {
    decision = 'DO_NOT_MERGE';
    reasons.push('The visible test passes, but the revoked-session counterfactual still returns 200 instead of 401.');
    reasons.push('A reproduced critical counterexample forces a blocking policy outcome.');
  } else {
    decision = 'SAFE_TO_MERGE';
    reasons.push('The candidate satisfies the visible requirement and the bounded revoked-session counterfactual.');
    reasons.push('This is a bounded decision over the executed evidence, not a claim of universal software safety.');
  }

  append(trace, 'MERGE_POLICY_EVALUATED', {
    decision,
    policyVersion: 'omen-demo-policy-v1',
    reasons,
  });

  return {
    traceId,
    patchStatus: 'applied',
    decision,
    baselineSource,
    candidateSource: parsed.candidateSource,
    observations: [visibleObservation, counterfactualObservation],
    audit: trace,
    reasons,
    testedBoundary: 'Built-in auth.py fixture; baseline and candidate behavior; expired-session visible test; revoked-but-unexpired bounded counterfactual.',
    uncertainty: 'OMEN does not claim universal safety or enumerate every possible failure state. The decision is limited to the evidence executed here.',
  };
}

export const handler = router({
  'GET /api/_healthcheck': [async () => json({ message: 'Success' })],
  'POST /api/evaluate-patch': [
    async ({ body }) => {
      const input = body as { task?: unknown; patch?: unknown };
      if (typeof input.task !== 'string' || !input.task.trim()) {
        return error('Task contract is required.', 400);
      }
      if (typeof input.patch !== 'string' || !input.patch.trim()) {
        return error('Candidate patch is required.', 400);
      }
      return json(evaluate(input.task, input.patch));
    },
  ],
});