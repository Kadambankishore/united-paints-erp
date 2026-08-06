# database.py
# This file connects our app to the PostgreSQL database on Railway
# Think of it like a telephone cable between our code and the database

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# -------------------------------------------------------------------
# DATABASE_URL is given automatically by Railway when you add Postgres
# It looks like: postgresql://user:password@host:5432/dbname
# -------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Railway sometimes gives "postgres://" but SQLAlchemy needs "postgresql://"
# This line fixes that automatically
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set! Please add PostgreSQL on Railway.")

# Create the database engine (the actual connection)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# SessionLocal = a "conversation session" with the database
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base = parent class for all our database table definitions
Base = declarative_base()


def get_db():
    """
    This is used by FastAPI to give each API request its own DB session.
    It automatically closes the session when the request is done.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all tables in the database (runs on first startup)"""
    from models import User, Invoice, InvoiceLineItem  # import here to avoid circular imports
    Base.metadata.create_all(bind=engine)
    print("✅ All database tables created (or already exist)")


def seed_default_users():
    """
    Create all default user accounts on first startup.
    Passwords can be changed later from the admin panel.
    """
    from models import User
    from auth import hash_password

    db = SessionLocal()

    # (username, password, role, rep_name, display_name)
    # role can be: "admin", "management", "rep"
    default_users = [
        ("muruga",              "Admin@2026",   "admin",      None,                      "Muruga (Admin)"),
        ("akshai_sir",          "Mgmt@2026",    "management", None,                      "Akshai Sir"),
        ("aakhash_sir",         "Mgmt@2026",    "management", None,                      "Aakhash Sir"),
        ("ashok_sir",           "Mgmt@2026",    "management", None,                      "Ashok Sir"),
        ("vijay",               "Rep@2026",     "rep",        "Vijay",                   "Vijay"),
        ("u_kannan",            "Rep@2026",     "rep",        "U. Kannan",               "U. Kannan"),
        ("l_sreenivasan",       "Rep@2026",     "rep",        "L. Sreenivasan",          "L. Sreenivasan"),
        ("l_sreenivasan_covai", "Rep@2026",     "rep",        "L. Sreenivasan (Covai)",  "L.S. Covai"),
        ("babu",                "Rep@2026",     "rep",        "Babu",                    "Babu"),
        ("t_dhinakaran",        "Rep@2026",     "rep",        "T. Dhinakaran",           "T. Dhinakaran"),
        ("deepak",              "Rep@2026",     "rep",        "Deepak",                  "Deepak"),
    ]

    created = 0
    for username, password, role, rep_name, display_name in default_users:
        exists = db.query(User).filter(User.username == username).first()
        if not exists:
            user = User(
                username=username,
                password_hash=hash_password(password),
                role=role,
                rep_name=rep_name,
                display_name=display_name,
                is_active=True
            )
            db.add(user)
            created += 1

    db.commit()
    db.close()
    print(f"✅ Users ready ({created} new accounts created)")
