from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_ALGORITHM = "HS256"
_TOKEN_DAYS = 30


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_token(operator_id: int, secret: str) -> str:
    return jwt.encode(
        {
            "sub": str(operator_id),
            "exp": datetime.now(timezone.utc) + timedelta(days=_TOKEN_DAYS),
        },
        secret,
        algorithm=_ALGORITHM,
    )


def decode_token(token: str, secret: str) -> int | None:
    """Return operator_id from a valid token, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, secret, algorithms=[_ALGORITHM])
        return int(payload["sub"])
    except jwt.PyJWTError:
        return None
