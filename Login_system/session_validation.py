"""Shared signed-session validation for login and RAG servers."""
from __future__ import annotations

import time
from typing import Any, Tuple

from Login_system.persistent_state import is_session_invalidated, touch_user_session

SESSION_ABSOLUTE_TIMEOUT = 86400  # 24 hours
SESSION_IDLE_TIMEOUT = 1800  # 30 minutes


def validate_session_payload(
    session_data: dict,
    *,
    update_activity: bool = True,
) -> Tuple[bool, str]:
    """Validate session has not expired or been invalidated."""
    if not isinstance(session_data, dict):
        return False, "Invalid session"

    session_id = session_data.get("session_id")
    if session_id and is_session_invalidated(str(session_id)):
        return False, "Session invalidated"

    created_at = float(session_data.get("created_at") or 0)
    last_activity = float(session_data.get("last_activity", created_at) or created_at)
    now = time.time()

    if now - created_at > SESSION_ABSOLUTE_TIMEOUT:
        return False, "Session expired (absolute timeout)"

    if now - last_activity > SESSION_IDLE_TIMEOUT:
        return False, "Session expired (idle timeout)"

    if update_activity:
        session_data["last_activity"] = now
        if session_id:
            touch_user_session(str(session_id), now)

    return True, ""


def load_and_validate_session_token(
    serializer: Any,
    token: str,
    *,
    update_activity: bool = True,
) -> Tuple[dict | None, str]:
    """Deserialize and validate a signed session cookie."""
    try:
        user = serializer.loads(token)
    except Exception:
        return None, "Invalid session"

    valid, err = validate_session_payload(user, update_activity=update_activity)
    if not valid:
        return None, err or "Invalid session"

    return user, ""
