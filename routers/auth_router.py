# routers/auth_router.py
# API endpoints for login, logout, and user management

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel
from typing import Optional

from database import get_db
from models import User
from auth import verify_password, create_token, hash_password, get_current_user, require_admin

router = APIRouter()


# -----------------------------------------------------------
# Request/Response data shapes (Pydantic models)
# -----------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class CreateUserRequest(BaseModel):
    username:     str
    password:     str
    role:         str          # admin / management / rep
    display_name: str
    rep_name:     Optional[str] = None


# -----------------------------------------------------------
# POST /api/auth/login
# -----------------------------------------------------------
@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """
    Login with username and password.
    Returns a token if credentials are correct.
    """
    # Step 1: Find user
    user = db.query(User).filter(
        User.username == req.username.strip().lower(),
        User.is_active == True
    ).first()

    if not user:
        raise HTTPException(status_code=401, detail="Username not found. Please check and try again.")

    # Step 2: Check password
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong password. Please try again.")

    # Step 3: Update last login time
    user.last_login = datetime.utcnow()
    db.commit()

    # Step 4: Create and return token
    token = create_token(
        user_id=user.id,
        username=user.username,
        role=user.role,
        display_name=user.display_name,
        rep_name=user.rep_name
    )

    return {
        "token":        token,
        "username":     user.username,
        "display_name": user.display_name,
        "role":         user.role,
        "rep_name":     user.rep_name
    }


# -----------------------------------------------------------
# GET /api/auth/me
# -----------------------------------------------------------
@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    """Returns info about currently logged-in user."""
    return current_user


# -----------------------------------------------------------
# POST /api/auth/change-password
# -----------------------------------------------------------
@router.post("/change-password")
def change_password(
    req: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Allows any logged-in user to change their own password."""
    user = db.query(User).filter(User.id == current_user["user_id"]).first()

    if not verify_password(req.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Old password is incorrect.")

    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")

    user.password_hash = hash_password(req.new_password)
    db.commit()
    return {"message": "✅ Password changed successfully!"}


# -----------------------------------------------------------
# GET /api/auth/users  (admin only)
# -----------------------------------------------------------
@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """Admin only: List all user accounts."""
    users = db.query(User).order_by(User.role, User.display_name).all()
    return [
        {
            "id":           u.id,
            "username":     u.username,
            "display_name": u.display_name,
            "role":         u.role,
            "rep_name":     u.rep_name,
            "is_active":    u.is_active,
            "last_login":   u.last_login.strftime("%d-%b-%Y %H:%M") if u.last_login else "Never"
        }
        for u in users
    ]


# -----------------------------------------------------------
# POST /api/auth/reset-password  (admin only)
# -----------------------------------------------------------
@router.post("/reset-password/{user_id}")
def reset_password(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """Admin only: Reset any user's password to the default."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Reset to default password based on role
    default_passwords = {
        "admin":      "Admin@2026",
        "management": "Mgmt@2026",
        "rep":        "Rep@2026"
    }
    new_pass = default_passwords.get(user.role, "Reset@2026")
    user.password_hash = hash_password(new_pass)
    db.commit()

    return {"message": f"✅ Password reset to: {new_pass}"}
