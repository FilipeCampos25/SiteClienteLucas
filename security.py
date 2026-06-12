from __future__ import annotations

import secrets
from typing import Optional

from fastapi import HTTPException, Request, status

CSRF_SESSION_KEY = "csrf_token"
CSRF_FORM_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


def get_csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_SESSION_KEY)
    if isinstance(token, str) and token:
        return token

    token = secrets.token_urlsafe(32)
    request.session[CSRF_SESSION_KEY] = token
    return token


def rotate_session(request: Request, *, admin_user: str) -> str:
    request.session.clear()
    request.session["admin_authed"] = True
    request.session["admin_user"] = admin_user
    return get_csrf_token(request)


async def csrf_protect(request: Request) -> None:
    expected = request.session.get(CSRF_SESSION_KEY)
    supplied: Optional[str] = request.headers.get(CSRF_HEADER)

    if not supplied:
        content_type = request.headers.get("content-type", "").lower()
        if (
            "application/x-www-form-urlencoded" in content_type
            or "multipart/form-data" in content_type
        ):
            form = await request.form()
            form_token = form.get(CSRF_FORM_FIELD)
            supplied = str(form_token) if form_token is not None else None

    if (
        not isinstance(expected, str)
        or not expected
        or not isinstance(supplied, str)
        or not supplied
        or not secrets.compare_digest(expected, supplied)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token CSRF ausente ou invalido.",
        )
