import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime
from uuid import UUID

from flagstaff_server.application.audit import AuditCursor
from flagstaff_server.domain.errors import InvalidValueError
from flagstaff_server.domain.ids import AuditEntryId

# Clients treat cursors as opaque strings. They aren't signed: editing one only moves where a
# page starts inside a log the caller may read anyway, so there is nothing to protect.


def encode_cursor(cursor: AuditCursor) -> str:
    payload = {"at": cursor.at.isoformat(), "entry": str(cursor.entry_id)}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(token: str) -> AuditCursor:
    try:
        payload = json.loads(urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        at = datetime.fromisoformat(payload["at"])
        entry_id = AuditEntryId(UUID(payload["entry"]))
    except (ValueError, KeyError, TypeError) as error:
        raise InvalidValueError("cursor is invalid") from error
    # Compared against timestamptz values, a naive time would silently mean UTC.
    if at.tzinfo is None:
        raise InvalidValueError("cursor is invalid")
    return AuditCursor(at, entry_id)
