# auth.py
# Handles passwords and login tokens

import os
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SECRET_KEY = os.getenv("SECRET_KEY", "unitedpaints-erp-super-secret-key-2026")
ALGORITHM = "HS256"
TOKEN_VALID_DAYS = 30

# pbkdf2_sha256 = secure, no external dependency, works everywhere
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

bearer_scheme = HTTPBearer()


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_token(user_id: int, username: str, role: str, display_name: str, rep_name: str = None) -> str:
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
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Session expired. Please login again.")


def get_current_user(credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)) -> dict:
    return decode_token(credentials.credentials)


def require_admin(credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)) -> dict:
    user = decode_token(credentials.credentials)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


def require_management_or_admin(credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)) -> dict:
    user = decode_token(credentials.credentials)
    if user.get("role") not in ("admin", "management"):
        raise HTTPException(status_code=403, detail="Management access required.")
    return user
