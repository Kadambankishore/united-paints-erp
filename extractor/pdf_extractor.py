# extractor/pdf_extractor.py
# Reads UC/UP invoice PDFs and converts them into structured data.
# Uses pdfplumber to read each page and extract invoice details.

import re
import pdfplumber
from typing import List, Dict, Any

# ---------------------------------------------------------------
# REP NAME DETECTION
# The rep code appears in the invoice. We map it to the full name.
# ---------------------------------------------------------------
REP_CODE_MAP = {
    "VIJAY":   "Vijay",
    "VJY":     "Vijay",
    "U.K":     "U. Kannan",
    "UK":      "U. Kannan",
    "L.S":     "L. Sreenivasan",
    "LS":      "L. Sreenivasan",
    "L.S.C":   "L. Sreenivasan (Covai)",
    "LSC":     "L. Sreenivasan (Covai)",
    "BABU":    "Babu",
    "TDK":     "T. Dhinakaran",
    "T.D.K":   "T. Dhinakaran",
    "DEEPAK":  "Deepak",
    "DPK":     "Deepak",
}

# Month number to label
MONTH_LABELS = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"
}


def clean_amount(value: str) -> float:
    """Convert '1,23,456.78' string to float 123456.78"""
    if not value:
        return 0.0
    cleaned = re.sub(r"[^\d.]", "", str(value))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def detect_rep(text: str) -> str:
    """Try to find the rep code in an invoice's text"""
    text_upper = text.upper()
    for code, name in REP_CODE_MAP.items():
        if re.search(r'\b' + re.escape(code) + r'\b', text_upper):
            return name
    return "Direct Order"


def extract_date_parts(date_str: str) -> Dict:
    """
    Parse 'DD-MM-YYYY' or 'DD/MM/YYYY' into parts.
    Returns dict with month, year, month_label
    """
    date_str = str(date_str).strip()
    # Try DD-MM-YYYY
    m = re.match(r"(\d{2})[-/](\d{2})[-/](\d{4})", date_str)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        label = f"{MONTH_LABELS.get(month, month)}-{year}"
        return {"day": day, "month": month, "year": year, "month_label": label}
    return {"day": "01", "month": "04", "year": "2026", "month_label": "Apr-2026"}


def extract_invoices_from_pdf(pdf_path: str, company: str) -> List[Dict[str, Any]]:
    """
    Main function: reads a PDF file and returns a list of invoice dictionaries.
    Each dictionary has the same structure as the BILLS array in Erp_Final.html.

    NOTE: UC and UP invoice PDFs have a similar layout.
    This extractor handles the standard format.
    If some invoices are missed, we can tune it - just report to buddy.
    """
    invoices = []

    with pdfplumber.open(pdf_path) as pdf:
        print(f"  📄 Reading {len(pdf.pages)} pages from {pdf_path}...")

        current_invoice = None

        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            lines = [line.strip() for line in text.split("\n") if line.strip()]

            # Each page in UC/UP PDFs = one invoice
            # Look for invoice number pattern
            inv_no = None
            inv_date = None
            buyer_name = None
            gstin = None
            place = None
            grand_total = 0.0
            taxable_value = 0.0
            cgst = 0.0
            sgst = 0.0
            igst = 0.0
            irn = ""
            products = []

            full_text = " ".join(lines)

            # --- Invoice Number ---
            inv_match = re.search(r"Invoice\s*No[:\.]?\s*(\S+)", full_text, re.IGNORECASE)
            if not inv_match:
                inv_match = re.search(r"Bill\s*No[:\.]?\s*(\S+)", full_text, re.IGNORECASE)
            if inv_match:
                inv_no = inv_match.group(1).strip()

            # --- Invoice Date ---
            date_match = re.search(r"(\d{2}[-/]\d{2}[-/]\d{4})", full_text)
            if date_match:
                inv_date = date_match.group(1)

            # --- Buyer Name (Bill To / Ship To) ---
            buyer_match = re.search(r"(?:Bill\s*To|Buyer)[:\s]+([^\n]+)", full_text, re.IGNORECASE)
            if buyer_match:
                buyer_name = buyer_match.group(1).strip()[:200]

            # --- GSTIN ---
            gstin_match = re.search(r"GSTIN[:\s]+([A-Z0-9]{15})", full_text, re.IGNORECASE)
            if gstin_match:
                gstin = gstin_match.group(1).strip()
                # party_uid = first 10 chars of GSTIN (company + state code)
                party_uid = gstin[:10] if gstin else f"NGSTIN_{buyer_name[:20] if buyer_name else 'UNKNOWN'}"
            else:
                party_uid = f"NGSTIN_{(buyer_name or 'UNKNOWN')[:20]}"

            # --- Place/City ---
            place_match = re.search(r"(?:Place|City|District)[:\s]+([A-Za-z ]+)", full_text, re.IGNORECASE)
            if place_match:
                place = place_match.group(1).strip()[:100]

            # --- Grand Total ---
            total_match = re.search(r"Grand\s*Total[:\s₹]*([\d,]+\.?\d*)", full_text, re.IGNORECASE)
            if not total_match:
                total_match = re.search(r"Total\s*Amount[:\s₹]*([\d,]+\.?\d*)", full_text, re.IGNORECASE)
            if total_match:
                grand_total = clean_amount(total_match.group(1))

            # --- Taxable Value ---
            tax_match = re.search(r"Taxable\s*(?:Value|Amount)[:\s₹]*([\d,]+\.?\d*)", full_text, re.IGNORECASE)
            if tax_match:
                taxable_value = clean_amount(tax_match.group(1))

            # --- CGST ---
            cgst_match = re.search(r"CGST[:\s₹]*([\d,]+\.?\d*)", full_text, re.IGNORECASE)
            if cgst_match:
                cgst = clean_amount(cgst_match.group(1))

            # --- SGST ---
            sgst_match = re.search(r"SGST[:\s₹]*([\d,]+\.?\d*)", full_text, re.IGNORECASE)
            if sgst_match:
                sgst = clean_amount(sgst_match.group(1))

            # --- IGST ---
            igst_match = re.search(r"IGST[:\s₹]*([\d,]+\.?\d*)", full_text, re.IGNORECASE)
            if igst_match:
                igst = clean_amount(igst_match.group(1))

            # --- IRN ---
            irn_match = re.search(r"IRN[:\s]+([a-f0-9]{8,})", full_text, re.IGNORECASE)
            if irn_match:
                irn = irn_match.group(1)[:200]

            # --- Rep Name ---
            rep_name = detect_rep(full_text)

            # --- Product Table ---
            # Try to extract table using pdfplumber
            try:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or len(row) < 3:
                            continue
                        # A product row usually has: SL, Product name, HSN, Qty, Rate, Amount
                        row_text = " ".join(str(c) for c in row if c)
                        # Skip header rows
                        if any(kw in row_text.upper() for kw in ["DESCRIPTION", "HSN", "S.NO", "ITEM", "PRODUCT"]):
                            continue
                        # Skip total rows
                        if any(kw in row_text.upper() for kw in ["TOTAL", "GRAND", "CGST", "SGST", "IGST"]):
                            continue

                        # Try to find amount in last column
                        amount_val = 0.0
                        for cell in reversed(row):
                            if cell:
                                amt = clean_amount(str(cell))
                                if amt > 0:
                                    amount_val = amt
                                    break

                        # Product name is usually in column 1 or 2
                        prod_name = ""
                        for cell in row[1:4]:
                            if cell and len(str(cell)) > 3 and not re.match(r"^\d+$", str(cell)):
                                prod_name = str(cell).strip()
                                break

                        if prod_name and amount_val > 0:
                            # Try to get quantity
                            qty = 0.0
                            for cell in row:
                                if cell:
                                    try:
                                        v = float(re.sub(r"[^\d.]", "", str(cell)))
                                        if 0 < v < 10000 and v != amount_val:
                                            qty = v
                                            break
                                    except Exception:
                                        pass

                            products.append({
                                "product": prod_name[:300],
                                "packing": "",
                                "quantity": str(qty),
                                "items": qty,
                                "rate": 0.0,
                                "amount": amount_val,
                                "hsn": "",
                                "gst_pct": "18"
                            })
            except Exception:
                pass  # If table extraction fails, we still save the invoice header

            # Only save if we got at least an invoice number or total
            if inv_no or grand_total > 0:
                date_parts = extract_date_parts(inv_date or "")
                invoices.append({
                    "company":       company,
                    "source_pdf":    pdf_path,
                    "pdf_page":      page_num,
                    "inv_no":        inv_no or f"P{page_num}",
                    "inv_date":      inv_date or "",
                    "month":         date_parts["month"],
                    "year":          date_parts["year"],
                    "month_label":   date_parts["month_label"],
                    "buyer_name":    buyer_name or "Unknown Party",
                    "party_uid":     party_uid,
                    "place":         place or "",
                    "rep_name":      rep_name,
                    "area_code":     "",
                    "grand_total":   grand_total,
                    "taxable_value": taxable_value,
                    "cgst":          cgst,
                    "sgst":          sgst,
                    "igst":          igst,
                    "irn":           irn,
                    "products":      products
                })

        print(f"  ✅ Extracted {len(invoices)} invoices from {page_num} pages")

    return invoices
