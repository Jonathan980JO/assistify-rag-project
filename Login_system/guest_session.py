"""Anonymous guest identity for public chat (per-browser conversation isolation)."""
from __future__ import annotations

import re
import secrets
import uuid

from fastapi import Request, Response

try:
    from config import ENFORCE_HTTPS, GUEST_ID_COOKIE
except Exception:
    ENFORCE_HTTPS = False
    GUEST_ID_COOKIE = "guest_id"

GUEST_OWNER_HEADER = "X-Guest-Owner"
_GUEST_ID_RE = re.compile(r"^guest_[0-9a-f]{32}$", re.IGNORECASE)
_GUEST_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def is_valid_guest_id(value: str | None) -> bool:
    if not value:
        return False
    return bool(_GUEST_ID_RE.match(str(value).strip()))


def new_guest_id() -> str:
    return f"guest_{uuid.uuid4().hex}"


def get_guest_id(request: Request) -> str | None:
    raw = request.cookies.get(GUEST_ID_COOKIE)
    if is_valid_guest_id(raw):
        return str(raw).strip()
    return None


def ensure_guest_id(request: Request, response: Response | None = None) -> str:
    existing = get_guest_id(request)
    if existing:
        return existing
    guest_id = new_guest_id()
    if response is not None:
        set_guest_cookie(response, guest_id)
    return guest_id


def set_guest_cookie(response: Response, guest_id: str) -> None:
    if not is_valid_guest_id(guest_id):
        guest_id = new_guest_id()
    response.set_cookie(
        key=GUEST_ID_COOKIE,
        value=guest_id,
        httponly=True,
        secure=ENFORCE_HTTPS,
        samesite="lax",
        max_age=_GUEST_COOKIE_MAX_AGE,
        path="/",
    )


def guest_rag_headers(request: Request, guest_id: str) -> dict:
    headers: dict[str, str] = {}
    csrf = request.headers.get("x-csrf-token") or request.cookies.get("csrf_token")
    if csrf:
        headers["x-csrf-token"] = csrf
    if is_valid_guest_id(guest_id):
        headers[GUEST_OWNER_HEADER] = guest_id
    return headers
