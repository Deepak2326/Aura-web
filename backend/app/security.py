"""Security helpers: password hashing (PBKDF2-HMAC-SHA256), JWT, sanitization.

PBKDF2 from the standard library is used instead of bcrypt to avoid native
dependencies while still providing a slow, salted KDF (260k iterations).
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

from jose import jwt

_PBKDF2_ITERATIONS = 260_000
_TAG_RE = re.compile(r"<[^>]*>")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# ---------------------------------------------------------------------------
# Input sanitization
# ---------------------------------------------------------------------------
def sanitize_text(value: str) -> str:
    """Single-line fields: strip HTML tags, control chars, collapse whitespace."""
    value = _TAG_RE.sub("", value)
    value = _CTRL_RE.sub("", value)
    return " ".join(value.split()).strip()


def sanitize_multiline(value: str) -> str:
    """Multi-line fields (message): strip tags/control chars but keep newlines."""
    value = _TAG_RE.sub("", value)
    value = _CTRL_RE.sub("", value)
    lines = [" ".join(line.split()) for line in value.splitlines()]
    return "\n".join(line for line in lines).strip()


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS).hex()
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt, digest = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(calc, digest)
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def create_access_token(*, secret: str, algorithm: str, expires_minutes: int, subject: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": subject, "role": role, "iat": now, "exp": now + timedelta(minutes=expires_minutes)}
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(*, secret: str, algorithm: str, token: str) -> dict:
    """Decode and validate a token. Raises jose.JWTError on failure."""
    return jwt.decode(token, secret, algorithms=[algorithm])


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
def hash_ip(ip: str) -> str:
    """Store only a hash of the client IP (audit without retaining PII)."""
    return hashlib.sha256(ip.encode()).hexdigest()
