"""
Authentication service: password hashing, JWT tokens, OTP generation/verification.
"""
import secrets
import hashlib
import datetime as dt
from typing import Optional

import bcrypt
import jwt

from app.config import settings


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

def create_access_token(user_id: str, extra: dict = None) -> str:
    """Create a signed JWT access token."""
    now = dt.datetime.utcnow()
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token. Returns payload dict or None."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ---------------------------------------------------------------------------
# OTP
# ---------------------------------------------------------------------------

def generate_otp(length: int = None) -> str:
    """Generate a cryptographically secure numeric OTP."""
    length = length or settings.OTP_LENGTH
    # Generate a random integer in range [10^(n-1), 10^n - 1]
    lower = 10 ** (length - 1)
    upper = (10 ** length) - 1
    return str(secrets.randbelow(upper - lower + 1) + lower)


def hash_otp(otp: str) -> str:
    """Hash an OTP using SHA-256. OTPs are short-lived so SHA-256 is fine."""
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


def verify_otp(otp: str, otp_hash: str) -> bool:
    """Verify an OTP against its hash."""
    return hashlib.sha256(otp.encode("utf-8")).hexdigest() == otp_hash


# ---------------------------------------------------------------------------
# Password reset tokens
# ---------------------------------------------------------------------------

def generate_reset_token() -> str:
    """Generate a secure random reset token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash a reset token using SHA-256."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(token: str, token_hash: str) -> bool:
    """Verify a reset token against its hash."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest() == token_hash
