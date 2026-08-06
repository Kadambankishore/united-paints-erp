# auth.py
# Handles: hashing passwords, creating login tokens, verifying tokens
# A "token" is like a digital ID card - once you login, you carry this
# token and show it with every request to prove you're logged in.

import os
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# -------------------------------------------------------------------
# SECRET KEY - This is used to sign tokens. Keep it secret!
# On Railway, you will set this as an environment variable.
# -------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "unitedpaints-erp-super-secret-key-2026")
ALGORITHM  = "HS256"
TOKEN_VALID_DAYS = 30   # Login stays active for 30 days

# Password hashing tool (bcrypt is very secure)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# This object is used by FastAPI to read the "Bearer token" from requests
bearer_scheme = HTTPBearer()


def hash_password(plain_password: str) -> str:
    """Convert plain text password to a secure hash. Never store plain passwords."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check if a plain text password matches the stored hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_token(user_id: int, username: str, role: str, display_name: str, rep_name: str = None) -> str:
    """
    Create a JWT token for a logged-in user.
    This token contains: who you are, your role, and when it expires.
    """
    expire = datetime.utcnow() + timedelta(days=TOKEN_VALID_DAYS)
    payload = {
        "sub":          username,
        "user_id":      user_id,
        "role":         role,
        "display_name": display_name,
        "rep_name":     rep_name,
        "exp":          expire
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Read and verify a JWT token.
    Returns the user info if valid, raises error if expired or invalid.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Your session has expired. Please login again."
        )


def get_current_user(credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)) -> dict:
    """
    Dependency used in API routes.
    Any route that uses this will automatically require a valid login token.
    """
    return decode_token(credentials.credentials)


def require_admin(credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)) -> dict:
    """
    Dependency for admin-only routes (like uploading PDFs).
    Returns user info if admin, raises error if not.
    """
    user = decode_token(credentials.credentials)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required for this action.")
    return user


def require_management_or_admin(credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)) -> dict:
    """
    Dependency for routes visible to admin + management (not reps).
    """
    user = decode_token(credentials.credentials)
    if user.get("role") not in ("admin", "management"):
        raise HTTPException(status_code=403, detail="Management access required.")
    return user
