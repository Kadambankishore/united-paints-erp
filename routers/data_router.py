# routers/data_router.py
# These are the API endpoints that send data to the dashboard.
# The dashboard calls these URLs to get its numbers.

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct
from typing import Optional

from database import get_db
from models import Invoice, InvoiceLineItem
from auth import get_current_user

router = APIRouter()


# ============================================================
# HELPER: Build base invoice query with role-based filtering
# This is used by multiple endpoints below
# ============================================================
def base_invoice_query(db, current_user, fy, company, month=None):
    """
    Builds a filtered SQLAlchemy query.
    - If rep: sees only their own invoices
    - If admin/management: sees all invoices
    """
    q = db.query(Invoice).filter(Invoice.financial_year == fy)

    if company != "ALL":
        q = q.filter(Invoice.company == company)
    if month:
        q = q.filter(Invoice.month_label == month)
    if current_user["role"] == "rep":
        q = q.filter(Invoice.rep_name == current_user["rep_name"])

    return q


def base_lineitem_query(db, current_user, fy, company, month=None):
    """Same but for line items (product details)"""
    q = db.query(InvoiceLineItem).filter(InvoiceLineItem.financial_year == fy)

    if company != "ALL":
        q = q.filter(InvoiceLineItem.company == company)
    if month:
        q = q.filter(InvoiceLineItem.month_label == month)
    if current_user["role"] == "rep":
        q = q.filter(InvoiceLineItem.rep_name == current_user["rep_name"])

    return q


# ============================================================
# GET /api/data/available-years
# Returns list of FYs that have invoice data
# ============================================================
@router.get("/available-years")
def get_available_years(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    rows = db.query(distinct(Invoice.financial_year)).all()
    years = sorted([r[0] for r in rows if r[0]], reverse=True)
    return {"years": years}


# ============================================================
# GET /api/data/summary
# Top-level KPIs: total revenue, invoice count, party count
# ============================================================
@router.get("/summary")
def get_summary(
    fy:      str = Query("2026-27"),
    company: str = Query("ALL"),
    month:   Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    q = base_invoice_query(db, current_user, fy, company, month)

    # Aggregate in one DB query (fast)
    result = q.with_entities(
        func.count(Invoice.id).label("invoice_count"),
        func.sum(Invoice.grand_total).label("total_revenue"),
        func.count(distinct(Invoice.party_uid)).label("unique_parties"),
        func.sum(Invoice.taxable_value).label("taxable_value"),
        func.sum(Invoice.cgst).label("total_cgst"),
        func.sum(Invoice.sgst).label("total_sgst"),
        func.sum(Invoice.igst).label("total_igst"),
    ).first()

    # Month-wise breakdown
    month_rows = q.with_entities(
        Invoice.month_label,
        Invoice.month,
        Invoice.year,
        func.sum(Invoice.grand_total).label("revenue"),
        func.count(Invoice.id).label("count"),
        func.count(distinct(Invoice.party_uid)).label("parties")
    ).group_by(Invoice.month_label, Invoice.month, Invoice.year)\
     .order_by(Invoice.year, Invoice.month).all()

    # Company split
    company_rows = q.with_entities(
        Invoice.company,
        func.sum(Invoice.grand_total).label("revenue"),
        func.count(Invoice.id).label("count")
    ).group_by(Invoice.company).all()

    return {
        "fy":             fy,
        "company_filter": company,
        "invoice_count":  result.invoice_count or 0,
        "total_revenue":  round(result.total_revenue or 0, 2),
        "unique_parties": result.unique_parties or 0,
        "taxable_value":  round(result.taxable_value or 0, 2),
        "total_gst":      round((result.total_cgst or 0) + (result.total_sgst or 0) + (result.total_igst or 0), 2),
        "month_breakdown": [
            {
                "month_label": r.month_label,
                "month":       r.month,
                "year":        r.year,
                "revenue":     round(r.revenue or 0, 2),
                "count":       r.count,
                "parties":     r.parties
            }
            for r in month_rows
        ],
        "company_split": [
            {
                "company": r.company,
                "revenue": round(r.revenue or 0, 2),
                "count":   r.count
            }
            for r in company_rows
        ]
    }


# ============================================================
# GET /api/data/bills
# List of invoices with pagination
# ============================================================
@router.get("/bills")
def get_bills(
    fy:        str = Query("2026-27"),
    company:   str = Query("ALL"),
    month:     Optional[str] = Query(None),
    rep:       Optional[str] = Query(None),
    party_uid: Optional[str] = Query(None),
    search:    Optional[str] = Query(None),
    page:      int = Query(1, ge=1),
    page_size: int = Query(100, le=500),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    q = base_invoice_query(db, current_user, fy, company, month)

    if rep:
        q = q.filter(Invoice.rep_name == rep)
    if party_uid:
        q = q.filter(Invoice.party_uid == party_uid)
    if search:
        q = q.filter(Invoice.buyer_name.ilike(f"%{search}%"))

    total = q.count()
    invoices = q.order_by(Invoice.inv_date.desc(), Invoice.company)\
                .offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "invoices": [
            {
                "id":             inv.id,
                "company":        inv.company,
                "inv_no":         inv.inv_no,
                "inv_date":       inv.inv_date,
                "month_label":    inv.month_label,
                "financial_year": inv.financial_year,
                "buyer_name":     inv.buyer_name,
                "party_uid":      inv.party_uid,
                "place":          inv.place,
                "rep_name":       inv.rep_name,
                "grand_total":    round(inv.grand_total or 0, 2),
                "taxable_value":  round(inv.taxable_value or 0, 2),
            }
            for inv in invoices
        ]
    }


# ============================================================
# GET /api/data/rep-performance
# Revenue per rep with rankings
# ============================================================
@router.get("/rep-performance")
def get_rep_performance(
    fy:      str = Query("2026-27"),
    company: str = Query("ALL"),
    month:   Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    q = base_invoice_query(db, current_user, fy, company, month)

    rows = q.with_entities(
        Invoice.rep_name,
        func.sum(Invoice.grand_total).label("revenue"),
        func.count(Invoice.id).label("invoice_count"),
        func.count(distinct(Invoice.party_uid)).label("party_count"),
        func.count(distinct(Invoice.place)).label("city_count")
    ).group_by(Invoice.rep_name)\
     .order_by(func.sum(Invoice.grand_total).desc()).all()

    total_revenue = sum(r.revenue or 0 for r in rows)

    return [
        {
            "rank":          i + 1,
            "rep_name":      r.rep_name or "Direct Order",
            "revenue":       round(r.revenue or 0, 2),
            "invoice_count": r.invoice_count,
            "party_count":   r.party_count,
            "city_count":    r.city_count,
            "revenue_pct":   round((r.revenue or 0) / total_revenue * 100, 1) if total_revenue else 0
        }
        for i, r in enumerate(rows)
    ]


# ============================================================
# GET /api/data/products
# Product movement - revenue and quantities per product
# ============================================================
@router.get("/products")
def get_products(
    fy:      str = Query("2026-27"),
    company: str = Query("ALL"),
    month:   Optional[str] = Query(None),
    group:   Optional[str] = Query(None),   # Filter by C01, C02 etc.
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    q = base_lineitem_query(db, current_user, fy, company, month)

    if group:
        q = q.filter(InvoiceLineItem.product_group == group)

    rows = q.with_entities(
        InvoiceLineItem.product,
        InvoiceLineItem.product_family,
        InvoiceLineItem.product_group,
        func.sum(InvoiceLineItem.items).label("total_items"),
        func.sum(InvoiceLineItem.amount).label("total_amount"),
        func.count(distinct(InvoiceLineItem.party_uid)).label("party_count"),
        func.count(distinct(InvoiceLineItem.invoice_id)).label("invoice_count")
    ).group_by(
        InvoiceLineItem.product,
        InvoiceLineItem.product_family,
        InvoiceLineItem.product_group
    ).order_by(func.sum(InvoiceLineItem.amount).desc()).all()

    return [
        {
            "product":        r.product,
            "product_family": r.product_family,
            "product_group":  r.product_group,
            "total_items":    round(r.total_items or 0, 2),
            "total_amount":   round(r.total_amount or 0, 2),
            "party_count":    r.party_count,
            "invoice_count":  r.invoice_count
        }
        for r in rows
    ]


# ============================================================
# GET /api/data/party-summary
# Top parties by revenue
# ============================================================
@router.get("/party-summary")
def get_party_summary(
    fy:      str = Query("2026-27"),
    company: str = Query("ALL"),
    month:   Optional[str] = Query(None),
    rep:     Optional[str] = Query(None),
    limit:   int = Query(50, le=500),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    q = base_invoice_query(db, current_user, fy, company, month)
    if rep:
        q = q.filter(Invoice.rep_name == rep)

    rows = q.with_entities(
        Invoice.party_uid,
        Invoice.buyer_name,
        Invoice.place,
        Invoice.rep_name,
        func.sum(Invoice.grand_total).label("revenue"),
        func.count(Invoice.id).label("invoice_count")
    ).group_by(
        Invoice.party_uid, Invoice.buyer_name, Invoice.place, Invoice.rep_name
    ).order_by(func.sum(Invoice.grand_total).desc()).limit(limit).all()

    return [
        {
            "party_uid":     r.party_uid,
            "buyer_name":    r.buyer_name,
            "place":         r.place,
            "rep_name":      r.rep_name,
            "revenue":       round(r.revenue or 0, 2),
            "invoice_count": r.invoice_count
        }
        for r in rows
    ]


# ============================================================
# GET /api/data/party-products/{party_uid}
# What products a specific party buys
# ============================================================
@router.get("/party-products/{party_uid}")
def get_party_products(
    party_uid: str,
    fy:      str = Query("2026-27"),
    company: str = Query("ALL"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    q = db.query(InvoiceLineItem).filter(
        InvoiceLineItem.financial_year == fy,
        InvoiceLineItem.party_uid == party_uid
    )
    if company != "ALL":
        q = q.filter(InvoiceLineItem.company == company)
    if current_user["role"] == "rep":
        q = q.filter(InvoiceLineItem.rep_name == current_user["rep_name"])

    rows = q.with_entities(
        InvoiceLineItem.product,
        InvoiceLineItem.product_group,
        InvoiceLineItem.product_family,
        func.sum(InvoiceLineItem.items).label("total_items"),
        func.sum(InvoiceLineItem.amount).label("total_amount"),
        func.count(InvoiceLineItem.id).label("line_count")
    ).group_by(
        InvoiceLineItem.product,
        InvoiceLineItem.product_group,
        InvoiceLineItem.product_family
    ).order_by(func.sum(InvoiceLineItem.amount).desc()).all()

    return [
        {
            "product":        r.product,
            "product_group":  r.product_group,
            "product_family": r.product_family,
            "total_items":    round(r.total_items or 0, 2),
            "total_amount":   round(r.total_amount or 0, 2),
            "line_count":     r.line_count
        }
        for r in rows
    ]
