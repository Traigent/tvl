"""DRAFT RFC 0012 §2.2/§2.6: validate a ``tvl-release-acceptance/1`` document.

Pure: schema check plus the expiry rule. It never reads platform state, so it cannot
decide authentication, approver authority or bindings (those are effect-time checks of
RFC 0012 §2.3, modelled by ``tvl.runtime_conditions``).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Mapping

from tvl.lints import parse_utc_instant
from tvl.schema import validator

MAX_VALIDITY = timedelta(days=7)


def validate_acceptance(doc: Any) -> List[Dict[str, Any]]:
    """Return closed diagnostics; an empty list means the document is valid."""
    def issue(path: List[Any], message: str) -> Dict[str, Any]:
        return {"code": "acceptance_record_invalid", "path": path, "message": message, "severity": "error"}

    if not isinstance(doc, Mapping):
        return [issue([], "acceptance record must be a mapping")]
    errors = sorted(validator("tvl-release-acceptance.schema.json").iter_errors(dict(doc)), key=lambda e: list(e.path))
    if errors:
        # Closed: name the field, never the rejected value.
        return [issue(list(e.absolute_path), "field does not satisfy the acceptance schema") for e in errors[:1]]
    decided, expires = parse_utc_instant(doc["decided_at"]), parse_utc_instant(doc["expires_at"])
    if decided is None or expires is None:
        return [issue(["decided_at"], "instants must be whole-second UTC instants")]
    if not decided < expires:
        return [issue(["expires_at"], "expires_at must be later than decided_at")]
    if expires - decided > MAX_VALIDITY:
        return [issue(["expires_at"], "expires_at - decided_at must be at most 7 days")]
    return []
