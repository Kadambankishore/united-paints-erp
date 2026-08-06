# routers/upload_router.py
# This endpoint receives PDF files, extracts invoice data, and saves to DB.
# Only admin (Muruga) can upload.

import os
import tempfile
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database import get_db
from models import Invoice, InvoiceLineItem
from auth import require_admin

router = APIRouter()


def calculate_financial_year(month: str, year: str) -> str:
    """
    Calculate financial year from month and year.
    Indian FY runs April to March.
    Example: month=04, year=2026 → "2026-27"
             month=01, year=2027 → "2026-27"
    """
    m = int(month)
    y = int(year)
    if m >= 4:
        return f"{y}-{str(y + 1)[2:]}"
    else:
        return f"{y - 1}-{str(y)[2:]}"


def save_invoice_to_db(db: Session, inv_data: dict, filename: str) -> bool:
    """
    Save one invoice (with its line items) to the database.
    Returns True if saved, False if it was a duplicate (already exists).
    """
    company = inv_data.get("company", "")
    inv_no  = str(inv_data.get("inv_no", ""))
    year    = str(inv_data.get("year", ""))
    month   = str(inv_data.get("month", ""))

    # Skip inter-company transfers and rent invoices
    if inv_data.get("_is_inter_company") or inv_data.get("_is_rent"):
        return False

    # Check for duplicate
    exists = db.query(Invoice).filter(
        Invoice.company == company,
        Invoice.inv_no  == inv_no,
        Invoice.year    == year
    ).first()
    if exists:
        return False

    fy = calculate_financial_year(month, year)

    invoice = Invoice(
        company        = company,
        inv_no         = inv_no,
        inv_date       = str(inv_data.get("inv_date", "")),
        month          = month,
        year           = year,
        month_label    = str(inv_data.get("month_label", "")),
        financial_year = fy,
        buyer_name     = str(inv_data.get("buyer_name", ""))[:300],
        party_uid      = str(inv_data.get("party_uid", ""))[:100],
        place          = str(inv_data.get("place", ""))[:150],
        rep_name       = str(inv_data.get("rep_name", "Direct Order"))[:100],
        area_code      = str(inv_data.get("area_code", ""))[:20],
        grand_total    = float(inv_data.get("grand_total", 0) or 0),
        taxable_value  = float(inv_data.get("taxable_value", 0) or 0),
        cgst           = float(inv_data.get("cgst", 0) or 0),
        sgst           = float(inv_data.get("sgst", 0) or 0),
        igst           = float(inv_data.get("igst", 0) or 0),
        irn            = str(inv_data.get("irn", ""))[:200],
        source_pdf     = filename[:300],
        pdf_page       = int(inv_data.get("pdf_page", 0) or 0)
    )
    db.add(invoice)
    db.flush()  # Get invoice.id before adding line items

    for prod in inv_data.get("products", []):
        li = InvoiceLineItem(
            invoice_id     = invoice.id,
            company        = company,
            financial_year = fy,
            month_label    = str(inv_data.get("month_label", "")),
            inv_date       = str(inv_data.get("inv_date", "")),
            rep_name       = str(inv_data.get("rep_name", "Direct Order"))[:100],
            party_uid      = str(inv_data.get("party_uid", ""))[:100],
            buyer_name     = str(inv_data.get("buyer_name", ""))[:300],
            place          = str(inv_data.get("place", ""))[:150],
            product        = str(prod.get("product", ""))[:400],
            packing        = str(prod.get("packing", ""))[:100],
            quantity_raw   = str(prod.get("quantity", ""))[:50],
            items          = float(prod.get("items", 0) or 0),
            rate           = float(prod.get("rate", 0) or 0),
            amount         = float(prod.get("amount", 0) or 0),
            hsn            = str(prod.get("hsn", ""))[:20],
            gst_pct        = str(prod.get("gst_pct", ""))[:10],
        )
        db.add(li)

    return True


@router.post("/pdf")
async def upload_pdf(
    file:    UploadFile = File(...),
    company: str        = Form("UC"),
    db: Session = Depends(get_db),
    current_user: dict  = Depends(require_admin)
):
    """
    Upload one invoice PDF.
    Extracts all invoices from it and saves them to the database.
    Only admin (Muruga) can do this.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    if company not in ("UC", "UP"):
        raise HTTPException(status_code=400, detail="Company must be UC or UP.")

    # Save the uploaded file temporarily
    content = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from extractor.pdf_extractor import extract_invoices_from_pdf
        invoices_data = extract_invoices_from_pdf(tmp_path, company)

        saved   = 0
        skipped = 0
        errors  = 0

        for inv_data in invoices_data:
            try:
                was_saved = save_invoice_to_db(db, inv_data, file.filename)
                if was_saved:
                    saved += 1
                else:
                    skipped += 1
            except Exception as e:
                errors += 1
                db.rollback()

        db.commit()

        return {
            "message":       f"✅ Done! Processed {file.filename}",
            "saved":         saved,
            "skipped_dupe":  skipped,
            "errors":        errors,
            "total_in_pdf":  len(invoices_data)
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
    finally:
        os.unlink(tmp_path)  # Always delete the temp file


@router.post("/bulk-pdfs")
async def upload_multiple_pdfs(
    files:   list[UploadFile] = File(...),
    company: str              = Form("UC"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """Upload multiple PDFs at once (for loading a full month batch)."""
    results = []
    for file in files:
        # Process each file
        content = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            from extractor.pdf_extractor import extract_invoices_from_pdf
            invoices_data = extract_invoices_from_pdf(tmp_path, company)
            saved = skipped = 0
            for inv_data in invoices_data:
                try:
                    if save_invoice_to_db(db, inv_data, file.filename):
                        saved += 1
                    else:
                        skipped += 1
                except Exception:
                    db.rollback()
            db.commit()
            results.append({"file": file.filename, "saved": saved, "skipped": skipped})
        except Exception as e:
            results.append({"file": file.filename, "error": str(e)})
        finally:
            os.unlink(tmp_path)

    total_saved = sum(r.get("saved", 0) for r in results)
    return {"results": results, "total_saved": total_saved}
