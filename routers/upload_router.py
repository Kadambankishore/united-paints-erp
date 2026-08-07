# routers/upload_router.py
# PDF upload endpoint — admin only
import os, re, tempfile
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Invoice, InvoiceLineItem
from auth import require_admin

router = APIRouter()


def parse_num(val) -> float:
    """Safely convert ANY value to float. Handles '5Bags', '15Pts', None, '' etc."""
    if val is None or val == '':
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        m = re.match(r'([\d.]+)', str(val).strip())
        return float(m.group(1)) if m else 0.0


def get_fy(month: str, year: str) -> str:
    m, y = int(month), int(year)
    return f"{y}-{str(y+1)[2:]}" if m >= 4 else f"{y-1}-{str(y)[2:]}"


def save_invoice_to_db(db: Session, inv: dict, filename: str) -> bool:
    """Save one invoice + its line items. Returns True if saved, False if duplicate."""
    company = inv.get("company", "")
    inv_no  = str(inv.get("inv_no", ""))
    year    = str(inv.get("year", ""))
    month   = str(inv.get("month", ""))

    if inv.get("_is_inter_company") or inv.get("_is_rent"):
        return False

    # Skip duplicates
    exists = db.query(Invoice).filter(
        Invoice.company == company,
        Invoice.inv_no  == inv_no,
        Invoice.year    == year
    ).first()
    if exists:
        return False

    fy = get_fy(month or "04", year or "2026")

    invoice = Invoice(
        company        = company,
        inv_no         = inv_no,
        inv_date       = str(inv.get("inv_date",      ""))[:20],
        month          = month,
        year           = year,
        month_label    = str(inv.get("month_label",   ""))[:20],
        financial_year = fy,
        buyer_name     = str(inv.get("buyer_name",    ""))[:300],
        party_uid      = str(inv.get("party_uid",     ""))[:100],
        place          = str(inv.get("place",          ""))[:150],
        rep_name       = str(inv.get("rep_name", "Direct Order"))[:100],
        area_code      = str(inv.get("area_code",      ""))[:20],
        grand_total    = parse_num(inv.get("grand_total")),
        taxable_value  = parse_num(inv.get("taxable_value")),
        cgst           = parse_num(inv.get("cgst")),
        sgst           = parse_num(inv.get("sgst")),
        igst           = parse_num(inv.get("igst")),
        irn            = str(inv.get("irn",            ""))[:200],
        source_pdf     = filename[:300],
        pdf_page       = int(parse_num(inv.get("pdf_page", 0)))
    )
    db.add(invoice)
    db.flush()  # get invoice.id

    for prod in inv.get("products", []):
        db.add(InvoiceLineItem(
            invoice_id     = invoice.id,
            company        = company,
            financial_year = fy,
            month_label    = str(inv.get("month_label", ""))[:20],
            inv_date       = str(inv.get("inv_date",    ""))[:20],
            rep_name       = str(inv.get("rep_name", "Direct Order"))[:100],
            party_uid      = str(inv.get("party_uid",   ""))[:100],
            buyer_name     = str(inv.get("buyer_name",  ""))[:300],
            place          = str(inv.get("place",        ""))[:150],
            product        = str(prod.get("product",     ""))[:400],
            packing        = str(prod.get("packing",     ""))[:100],
            quantity_raw   = str(prod.get("quantity",    ""))[:50],
            items          = parse_num(prod.get("items")),    # ← handles "5Bags", "15Pts"
            rate           = parse_num(prod.get("rate")),
            amount         = parse_num(prod.get("amount")),
            hsn            = str(prod.get("hsn",         ""))[:20],
            gst_pct        = str(prod.get("gst_pct",     ""))[:10],
        ))

    return True


@router.post("/pdf")
async def upload_pdf(
    file:    UploadFile = File(...),
    company: str        = Form("UC"),
    db: Session         = Depends(get_db),
    current_user: dict  = Depends(require_admin)
):
    """Upload one invoice PDF. Extract → save to database. Admin only."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files accepted.")
    if company not in ("UC", "UP"):
        raise HTTPException(status_code=400, detail="Company must be UC or UP.")

    content = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from extractor.pdf_extractor import extract_invoices_from_pdf
        invoices_data = extract_invoices_from_pdf(tmp_path, company)

        saved = skipped = errors = 0
        for inv in invoices_data:
            try:
                if save_invoice_to_db(db, inv, file.filename):
                    saved += 1
                else:
                    skipped += 1
            except Exception as e:
                errors += 1
                db.rollback()
                print(f"  Error saving inv {inv.get('inv_no')}: {e}")

        db.commit()
        return {
            "message":      f"✅ Done! Processed {file.filename}",
            "saved":        saved,
            "skipped_dupe": skipped,
            "errors":       errors,
            "total_in_pdf": len(invoices_data)
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {e}")
    finally:
        os.unlink(tmp_path)


@router.post("/bulk-pdfs")
async def upload_bulk(
    files:   list[UploadFile] = File(...),
    company: str              = Form("UC"),
    db: Session               = Depends(get_db),
    current_user: dict        = Depends(require_admin)
):
    """Upload multiple PDFs at once."""
    results = []
    for file in files:
        content = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(content); tmp_path = tmp.name
        try:
            from extractor.pdf_extractor import extract_invoices_from_pdf
            invoices = extract_invoices_from_pdf(tmp_path, company)
            saved = skipped = 0
            for inv in invoices:
                try:
                    if save_invoice_to_db(db, inv, file.filename): saved += 1
                    else: skipped += 1
                except Exception: db.rollback()
            db.commit()
            results.append({"file": file.filename, "saved": saved, "skipped": skipped})
        except Exception as e:
            results.append({"file": file.filename, "error": str(e)})
        finally:
            os.unlink(tmp_path)

    return {"results": results, "total_saved": sum(r.get("saved", 0) for r in results)}
