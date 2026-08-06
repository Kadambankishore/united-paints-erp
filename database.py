# database.py
import os
import time
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Railway provides DATABASE_URL automatically when PostgreSQL is added
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Railway uses "postgres://" but SQLAlchemy needs "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "On Railway: click your app → Variables → Add Reference → Postgres → DATABASE_URL"
    )

# Create engine with connection pool settings suitable for Railway
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,       # Check connection is alive before using
    pool_recycle=300,         # Recycle connections every 5 minutes
    connect_args={"connect_timeout": 10}  # 10 second connection timeout
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Give API routes a database session. Closes automatically when done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def wait_for_db(max_retries: int = 10, delay: int = 3):
    """
    Wait for the database to be ready.
    Railway sometimes needs a few seconds before PostgreSQL accepts connections.
    """
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"✅ Database connection successful!")
            return True
        except Exception as e:
            if attempt < max_retries:
                print(f"⏳ Database not ready yet (attempt {attempt}/{max_retries}). Waiting {delay}s... Error: {e}")
                time.sleep(delay)
            else:
                print(f"❌ Could not connect to database after {max_retries} attempts: {e}")
                raise
    return False


def create_tables():
    """Create all database tables if they don't exist."""
    from models import User, Invoice, InvoiceLineItem
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables ready")


def seed_default_users():
    """Create default login accounts on first startup."""
    from models import User
    from auth import hash_password

    db = SessionLocal()
    try:
        default_users = [
            ("muruga",              "Admin@2026",  "admin",      None,                      "Muruga (Admin)"),
            ("akshai_sir",          "Mgmt@2026",   "management", None,                      "Akshai Sir"),
            ("aakhash_sir",         "Mgmt@2026",   "management", None,                      "Aakhash Sir"),
            ("ashok_sir",           "Mgmt@2026",   "management", None,                      "Ashok Sir"),
            ("vijay",               "Rep@2026",    "rep",        "Vijay",                   "Vijay"),
            ("u_kannan",            "Rep@2026",    "rep",        "U. Kannan",               "U. Kannan"),
            ("l_sreenivasan",       "Rep@2026",    "rep",        "L. Sreenivasan",          "L. Sreenivasan"),
            ("l_sreenivasan_covai", "Rep@2026",    "rep",        "L. Sreenivasan (Covai)",  "L.S. Covai"),
            ("babu",                "Rep@2026",    "rep",        "Babu",                    "Babu"),
            ("t_dhinakaran",        "Rep@2026",    "rep",        "T. Dhinakaran",           "T. Dhinakaran"),
            ("deepak",              "Rep@2026",    "rep",        "Deepak",                  "Deepak"),
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
        print(f"✅ Users ready ({created} new accounts created)")
    finally:
        db.close()
