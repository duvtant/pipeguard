"""Shared API dependencies. Admin and test-mode endpoints need the X-Admin-Token header."""
import hmac

from fastapi import Header, HTTPException

from core.config import get_settings

settings = get_settings()


def require_admin(x_admin_token: str | None = Header(default=None)):
    """Open when ADMIN_TOKEN is empty (local dev). On the server the preflight must check admin_token_set."""
    if settings.admin_token and not hmac.compare_digest(x_admin_token or "", settings.admin_token):
        raise HTTPException(401, "invalid admin token")
