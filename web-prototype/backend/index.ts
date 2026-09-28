import { createHash, randomUUID } from 'node:crypto';
import { router, json, error } from '@appdeploy/sdk';

type Candidate = {
  denyExpired: boolean;
  denyRevoked: boolean;
  requireValidSignature: boolean;
};

type Session = {
  expired: boolean;
  revoked: boolean;
  signatureValid: boolean;
};

function baselineAuthorize(session: Session) {
  if (!session.signatureValid) return 401;
  return 200;
}

function candidateAuthorize(session: Session, candidate: Candidate) {
  if (candidate.requireValidSignature && !session.signatureValid) return 401;
  if (candidate.denyExpired && session.expired) return 401;
  if (candidate.denyRevoked && session.revoked) return 401;
  return 200;
}

function candidateSource(candidate: Candidate) {
  return [
    'function authorize(session) {',
    candidate.requireValidSignature ? '  if (!session.signatureValid) return 401;' : '',
    candidate.denyExpired ? '  if (session.expired) return 401;' : '',
    candidate.denyRevoked ? '  if (session.revoked) return 401;' : '',
    '  return 200;',
    '}',
  ].filter(Boolean).join('\n');
}

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

function execute(candidate: Candidate) {
  const visibleSession: Session = { expired: true, revoked: false, signatureValid: true };
  const revokedSession: Session = { expired: false, revoked: true, signatureValid: true };

  const observations = [
    {
      name: 'Visible expired-session test',
      baselineStatus: baselineAuthorize(visibleSession),
      candidateStatus: candidateAuthorize(visibleSession, candidate),
      expectedStatus: 401,
      passed: candidateAuthorize(visibleSession, candidate) === 401,
    },
    {
      name: 'Revoked-session counterfactual',
      baselineStatus: baselineAuthorize(revokedSession),
      candidateStatus: candidateAuthorize(revokedSession, candidate),
      expectedStatus: 401,
      passed: candidateAuthorize(revokedSession, candidate) === 401,
    },
  ];

  const traceId = randomUUID();
  const audit: Array<{ sequence: number; event: string; digest: string; previous: string }> = [];

  append(audit, 'EXECUTION_INTENT', { traceId, candidate: candidateSource(candidate) });
  append(audit, 'BASELINE_EXECUTED', {
    visible: observations[0].baselineStatus,
    counterfactual: observations[1].baselineStatus,
  });
  append(audit, 'CANDIDATE_PATCH_PREPARED', { sourceDigest: sha(candidateSource(candidate)) });
  append(audit, 'VISIBLE_TESTS_EXECUTED', observations[0]);
  append(audit, 'COUNTERFACTUAL_PROBE_EXECUTED', observations[1]);
  append(audit, 'EVIDENCE_PRESERVED', {
    visiblePassed: observations[0].passed,
    counterfactualPassed: observations[1].passed,
  });

  let decision: 'SAFE_TO_MERGE' | 'DO_NOT_MERGE';
  const reasons: string[] = [];

  if (!observations[0].passed) {
    decision = 'DO_NOT_MERGE';
    reasons.push('The candidate fails the declared expired-session requirement.');
  } else if (!observations[1].passed) {
    decision = 'DO_NOT_MERGE';
    reasons.push('The visible test passes, but the revoked-session counterfactual still authorizes access.');
  } else {
    decision = 'SAFE_TO_MERGE';
    reasons.push('The candidate denies both the visible expired-session case and the bounded revoked-session counterfactual.');
  }

  append(audit, 'MERGE_POLICY_EVALUATED', { decision, reasons });

  return { traceId, decision, candidateSource: candidateSource(candidate), observations, audit, reasons };
}

export const handler = router({
  'GET /api/_healthcheck': [async () => json({ message: 'Success' })],
  'POST /api/run': [
    async ({ body }) => {
      const input = body as { candidate?: Partial<Candidate> };
      const candidate = input.candidate;
      if (!candidate) return error('Candidate patch is required.', 400);
      for (const key of ['denyExpired', 'denyRevoked', 'requireValidSignature'] as const) {
        if (typeof candidate[key] !== 'boolean') return error('Invalid candidate rule: ' + key, 400);
      }
      return json(execute(candidate as Candidate));
    },
  ],
});