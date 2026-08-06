# models.py
# These are our database TABLE definitions.
# Think of each class here as one Excel sheet in the database.

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


# ============================================================
# TABLE 1: users
# Stores all login accounts (Muruga, sirs, reps)
# ============================================================
class User(Base):
    __tablename__ = "users"

    id           = Column(Integer, primary_key=True, index=True)
    username     = Column(String(50),  unique=True, nullable=False, index=True)
    password_hash= Column(String(200), nullable=False)
    role         = Column(String(20),  nullable=False)   # admin / management / rep
    rep_name     = Column(String(100), nullable=True)    # matches rep_name in invoices (for reps only)
    display_name = Column(String(100), nullable=False)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    last_login   = Column(DateTime, nullable=True)


# ============================================================
# TABLE 2: invoices
# One row = one invoice header (party, date, total, etc.)
# ============================================================
class Invoice(Base):
    __tablename__ = "invoices"

    id             = Column(Integer, primary_key=True, index=True)
    company        = Column(String(10),  nullable=False, index=True)   # UC or UP
    inv_no         = Column(String(50),  nullable=False, index=True)
    inv_date       = Column(String(20),  nullable=False)               # DD-MM-YYYY
    month          = Column(String(2),   nullable=False)               # "04"
    year           = Column(String(4),   nullable=False)               # "2026"
    month_label    = Column(String(20),  nullable=False, index=True)   # "Apr-2026"
    financial_year = Column(String(10),  nullable=False, index=True)   # "2026-27"

    buyer_name     = Column(String(300), nullable=False)
    party_uid      = Column(String(100), nullable=False, index=True)
    place          = Column(String(150), nullable=True)
    rep_name       = Column(String(100), nullable=True,  index=True)
    area_code      = Column(String(20),  nullable=True)

    grand_total    = Column(Float, default=0.0)
    taxable_value  = Column(Float, default=0.0)
    cgst           = Column(Float, default=0.0)
    sgst           = Column(Float, default=0.0)
    igst           = Column(Float, default=0.0)

    irn            = Column(String(200), nullable=True)
    source_pdf     = Column(String(300), nullable=True)
    pdf_page       = Column(Integer,     default=0)

    created_at     = Column(DateTime, default=datetime.utcnow)

    # One invoice has many line items (products)
    line_items = relationship("InvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan")

    # Combined unique check: same company + invoice number + year = duplicate
    __table_args__ = (
        Index("ix_company_inv_year", "company", "inv_no", "year", unique=True),
    )


# ============================================================
# TABLE 3: invoice_line_items
# One row = one product line inside an invoice
# (One invoice can have many products)
# ============================================================
class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"

    id             = Column(Integer, primary_key=True, index=True)
    invoice_id     = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)

    # Copied from invoice header (for faster filtering without JOIN)
    company        = Column(String(10),  index=True)
    financial_year = Column(String(10),  index=True)
    month_label    = Column(String(20),  index=True)
    inv_date       = Column(String(20))
    rep_name       = Column(String(100), index=True)
    party_uid      = Column(String(100), index=True)
    buyer_name     = Column(String(300))
    place          = Column(String(150))

    # Product details
    product        = Column(String(400), index=True)
    packing        = Column(String(100))
    quantity_raw   = Column(String(50))
    items          = Column(Float, default=0.0)   # number of units
    rate           = Column(Float, default=0.0)
    amount         = Column(Float, default=0.0)
    hsn            = Column(String(20))
    gst_pct        = Column(String(10))

    # Product classification (filled from product master)
    product_family = Column(String(150), nullable=True)
    product_group  = Column(String(10),  nullable=True)   # C01, C02 ... C23

    invoice = relationship("Invoice", back_populates="line_items")
