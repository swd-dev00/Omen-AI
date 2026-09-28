from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuditRecord:
    trace_id: str
    sequence: int
    event_type: str
    artifact_digest: str
    previous_record_digest: str | None
    record_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditTrail:
    """Append-only, per-trace hash chain.

    This plane preserves what was observed. It does not execute probes and it
    does not decide whether an action is permitted.
    """

    def __init__(self, trace_id: str):
        self.trace_id = trace_id
        self._records: list[AuditRecord] = []

    @property
    def records(self) -> tuple[AuditRecord, ...]:
        return tuple(self._records)

    def append(self, event_type: str, artifact: Any) -> AuditRecord:
        artifact_digest = _digest(artifact)
        previous = self._records[-1].record_digest if self._records else None
        body = {
            "trace_id": self.trace_id,
            "sequence": len(self._records),
            "event_type": event_type,
            "artifact_digest": artifact_digest,
            "previous_record_digest": previous,
        }
        record = AuditRecord(record_digest=_digest(body), **body)
        self._records.append(record)
        return record

    def verify(self) -> bool:
        previous: str | None = None
        for index, record in enumerate(self._records):
            if record.sequence != index or record.previous_record_digest != previous:
                return False
            body = {
                "trace_id": record.trace_id,
                "sequence": record.sequence,
                "event_type": record.event_type,
                "artifact_digest": record.artifact_digest,
                "previous_record_digest": record.previous_record_digest,
            }
            if _digest(body) != record.record_digest:
                return False
            previous = record.record_digest
        return True

    def to_list(self) -> list[dict[str, Any]]:
        return [record.to_dict() for record in self._records]
