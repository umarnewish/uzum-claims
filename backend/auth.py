"""Stateless JWT decode for Phase 0.

Validates a vendex-issued JWT using the shared SECRET_KEY and returns the
user_id. Does NOT call back into vendex to verify the session is still
active — that upgrade lands in Phase 1 once vendex exposes /api/me.

Token can arrive via either:
  - Authorization: Bearer <jwt>  (matches vendex frontend api.js)
  - Cookie: vendex_token=<jwt>    (in case we move to cookie-based SSO later)
"""
from typing import Optional

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.config import get_settings

settings = get_settings()
bearer = HTTPBearer(auto_error=False)


def _decode(token: str) -> int:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )


async def get_current_user_id(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    vendex_token: Optional[str] = Cookie(default=None),
) -> int:
    token = creds.credentials if creds else vendex_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing auth token",
        )
    return _decode(token)
