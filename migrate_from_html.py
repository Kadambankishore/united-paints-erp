"""
migrate_from_html.py
====================
Run this ONE TIME to load your existing April-July 2026 data
from Erp_Final.html into the PostgreSQL database.

After migration, all future data comes through the daily PDF upload.

HOW TO RUN:
    python migrate_from_html.py "path/to/Erp_Final.html"

Example:
    python migrate_from_html.py "C:/Users/Muruga/Desktop/Erp_Final.html"
"""

import json
import sys
import os
import re

# Add project root to path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()  # Load DATABASE_URL from .env file

from database import SessionLocal, create_tables, seed_default_users
from models import Invoice, InvoiceLineItem


def calculate_financial_year(month: str, year: str) -> str:
    """April-March Indian financial year"""
    m = int(month)
    y = int(year)
    if m >= 4:
        return f"{y}-{str(y + 1)[2:]}"
    else:
        return f"{y - 1}-{str(y)[2:]}"


def migrate(html_path: str):
    print(f"\n{'='*60}")
    print("  United Paints ERP — Data Migration")
    print(f"{'='*60}\n")

    # ---- Step 1: Read the HTML file ----
    if not os.path.exists(html_path):
        print(f"❌ File not found: {html_path}")
        print("   Please check the path and try again.")
        sys.exit(1)

    print(f"📂 Reading: {html_path}")
    with open(html_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # ---- Step 2: Extract the BILLS JSON array ----
    bills_json = ""
    for line in lines:
        if line.strip().startswith("const BILLS=["):
            # Remove "const BILLS=" from start and ";" from end
            bills_json = line.strip()
            bills_json = re.sub(r"^const BILLS=", "", bills_json)
            bills_json = bills_json.rstrip(";").rstrip()
            break

    if not bills_json:
        print("❌ Could not find invoice data in the HTML file.")
        print("   Make sure you are using the correct Erp_Final.html file.")
        sys.exit(1)

    bills = json.loads(bills_json)
    print(f"✅ Found {len(bills)} total records in HTML\n")

    # ---- Step 3: Set up database ----
    print("🔧 Setting up database tables...")
    create_tables()
    seed_default_users()
    print()

    # ---- Step 4: Insert invoices ----
    db = SessionLocal()
    saved   = 0
    skipped = 0
    errors  = 0

    print(f"📥 Loading invoices into database...")
    print(f"   (This may take 1-2 minutes for large files)\n")

    for i, inv in enumerate(bills):
        # Skip inter-company transfers (UC→UP supply, not customer sales)
        if inv.get("_is_inter_company") or inv.get("_is_rent"):
            skipped += 1
            continue

        company = inv.get("company", "")
        inv_no  = str(inv.get("inv_no", ""))
        year    = str(inv.get("year", ""))
        month   = str(inv.get("month", ""))

        # Check for duplicate
        exists = db.query(Invoice).filter(
            Invoice.company == company,
            Invoice.inv_no  == inv_no,
            Invoice.year    == year
        ).first()
        if exists:
            skipped += 1
            continue

        try:
            fy = calculate_financial_year(month, year)

            invoice = Invoice(
                company        = company,
                inv_no         = inv_no,
                inv_date       = str(inv.get("inv_date", "")),
                month          = month,
                year           = year,
                month_label    = str(inv.get("month_label", "")),
                financial_year = fy,
                buyer_name     = str(inv.get("buyer_name", ""))[:300],
                party_uid      = str(inv.get("party_uid", ""))[:100],
                place          = str(inv.get("place", ""))[:150],
                rep_name       = str(inv.get("rep_name", "Direct Order"))[:100],
                area_code      = str(inv.get("area_code", ""))[:20],
                grand_total    = float(inv.get("grand_total", 0) or 0),
                taxable_value  = float(inv.get("taxable_value", 0) or 0),
                cgst           = float(inv.get("cgst", 0) or 0),
                sgst           = float(inv.get("sgst", 0) or 0),
                igst           = float(inv.get("igst", 0) or 0),
                irn            = str(inv.get("irn", ""))[:200],
                source_pdf     = str(inv.get("source_pdf", ""))[:300],
                pdf_page       = int(inv.get("pdf_page", 0) or 0)
            )
            db.add(invoice)
            db.flush()

            # Insert line items (products)
            for prod in inv.get("products", []):
                li = InvoiceLineItem(
                    invoice_id     = invoice.id,
                    company        = company,
                    financial_year = fy,
                    month_label    = str(inv.get("month_label", "")),
                    inv_date       = str(inv.get("inv_date", "")),
                    rep_name       = str(inv.get("rep_name", "Direct Order"))[:100],
                    party_uid      = str(inv.get("party_uid", ""))[:100],
                    buyer_name     = str(inv.get("buyer_name", ""))[:300],
                    place          = str(inv.get("place", ""))[:150],
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

            saved += 1

            # Commit every 200 invoices (so progress is saved as we go)
            if saved % 200 == 0:
                db.commit()
                print(f"   ✅ {saved} invoices saved so far...")

        except Exception as e:
            errors += 1
            db.rollback()
            print(f"   ⚠️  Error on invoice {inv_no}: {e}")

    # Final commit
    db.commit()
    db.close()

    print(f"\n{'='*60}")
    print("  Migration Complete!")
    print(f"{'='*60}")
    print(f"  ✅ Invoices saved:   {saved}")
    print(f"  ⏭️  Skipped:         {skipped} (duplicates or inter-company)")
    print(f"  ❌ Errors:           {errors}")
    print(f"\n  You can now start the server and access the dashboard!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python migrate_from_html.py <path_to_Erp_Final.html>")
        print("Example: python migrate_from_html.py Erp_Final.html")
        sys.exit(1)

    migrate(sys.argv[1])
