# main.py
import os
import json
import re
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from database import create_tables, seed_default_users, wait_for_db
from routers import auth_router, data_router, upload_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 United Paints ERP starting...")
    try:
        wait_for_db()
        create_tables()
        seed_default_users()
        print("✅ Startup complete!")
    except Exception as e:
        print(f"⚠️  Startup warning: {e}")
    yield
    print("👋 Shutting down.")


app = FastAPI(title="United Paints ERP", version="2.0.0",
              lifespan=lifespan, docs_url="/api/docs", redoc_url=None)

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(auth_router.router,   prefix="/api/auth",   tags=["Auth"])
app.include_router(data_router.router,   prefix="/api/data",   tags=["Data"])
app.include_router(upload_router.router, prefix="/api/upload", tags=["Upload"])


def _page(title, body):
    return f"""<!DOCTYPE html><html><head><title>{title}</title></head>
<body style='font-family:-apple-system,sans-serif;background:#0A1628;color:#fff;
display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0'>
<div style='background:#1a2744;border-radius:16px;padding:40px 48px;max-width:560px;
text-align:center;width:90%'>
<div style='font-size:48px;margin-bottom:12px'>🏭</div>
<h1 style='color:#fff;margin-bottom:6px'>United Paints ERP</h1>
<h2 style='color:#4A9EE0;margin-bottom:28px;font-weight:400'>{title}</h2>
{body}</div></body></html>"""


def parse_num(val):
    """Safely convert any value to float. Handles '7Bags', '15Pts', None, etc."""
    if val is None or val == '':
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        m = re.match(r'([\d.]+)', str(val).strip())
        return float(m.group(1)) if m else 0.0


# ── Health ──────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {"status": "ok", "message": "United Paints ERP is running!"}


# ── Setup (tables + users) ──────────────────────────────────────────
@app.get("/setup")
def setup_database():
    results = []
    try:
        wait_for_db(max_retries=5, delay=2)
        results.append("✅ Database connected!")
    except Exception as e:
        return HTMLResponse(_page("❌ DB failed", f"<p style='color:#f66'>{e}</p>"), 500)
    try:
        create_tables();       results.append("✅ Tables ready!")
    except Exception as e:     results.append(f"⚠️ Tables: {e}")
    try:
        seed_default_users();  results.append("✅ Users created!")
    except Exception as e:     results.append(f"⚠️ Users: {e}")
    body = "".join(f"<p style='font-size:17px;margin:8px 0'>{r}</p>" for r in results)
    body += "<br><a href='/migrate' style='color:#4A9EE0'>→ Load invoice data next</a>"
    return HTMLResponse(_page("Setup done", body))


# ── Migrate (Erp_Final.html → PostgreSQL) ───────────────────────────
@app.get("/migrate")
def migrate_html_data():
    html_path = "static/Erp_Final.html"
    if not os.path.exists(html_path):
        return HTMLResponse(_page("File missing", "<p>static/Erp_Final.html not found.</p>"), 404)

    # Extract BILLS array from HTML
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        bills_json = ""
        for line in lines:
            if line.strip().startswith("const BILLS=["):
                bills_json = re.sub(r"^const BILLS=", "", line.strip()).rstrip(";").rstrip()
                break
        if not bills_json:
            return HTMLResponse(_page("Parse error", "<p>BILLS data not found in HTML.</p>"), 500)
        bills = json.loads(bills_json)
    except Exception as e:
        return HTMLResponse(_page("Read error", f"<p>{e}</p>"), 500)

    from database import SessionLocal
    from models import Invoice, InvoiceLineItem

    def get_fy(month, year):
        m, y = int(month), int(year)
        return f"{y}-{str(y+1)[2:]}" if m >= 4 else f"{y-1}-{str(y)[2:]}"

    db = SessionLocal()
    saved = skipped = errors = 0

    try:
        for inv in bills:
            # Skip inter-company and rent invoices
            if inv.get("_is_inter_company") or inv.get("_is_rent"):
                skipped += 1; continue

            company = str(inv.get("company", ""))
            inv_no  = str(inv.get("inv_no",  ""))
            year    = str(inv.get("year",    ""))
            month   = str(inv.get("month",   ""))

            # Skip duplicates
            exists = db.query(Invoice).filter(
                Invoice.company == company,
                Invoice.inv_no  == inv_no,
                Invoice.year    == year
            ).first()
            if exists:
                skipped += 1; continue

            try:
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
                    source_pdf     = str(inv.get("source_pdf",     ""))[:300],
                    pdf_page       = int(parse_num(inv.get("pdf_page")))
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
                        product        = str(prod.get("product",    ""))[:400],
                        packing        = str(prod.get("packing",    ""))[:100],
                        quantity_raw   = str(prod.get("quantity",   ""))[:50],
                        items          = parse_num(prod.get("items")),   # ← KEY FIX: "7Bags"→7.0
                        rate           = parse_num(prod.get("rate")),
                        amount         = parse_num(prod.get("amount")),
                        hsn            = str(prod.get("hsn",        ""))[:20],
                        gst_pct        = str(prod.get("gst_pct",    ""))[:10],
                    ))

                saved += 1
                if saved % 200 == 0:
                    db.commit()
                    print(f"  Migrated {saved} invoices...")

            except Exception as e:
                errors += 1
                db.rollback()
                print(f"  Error on inv {inv_no}: {e}")

        db.commit()
    finally:
        db.close()

    color = "#4ade80" if errors == 0 else "#f87171"
    body = f"""
    <p style='font-size:18px;margin:8px 0'>✅ Invoices saved: <strong>{saved}</strong></p>
    <p style='font-size:18px;margin:8px 0'>⏭️  Skipped: <strong>{skipped}</strong></p>
    <p style='font-size:18px;margin:8px 0;color:{color}'>
      {'✅' if errors==0 else '❌'} Errors: <strong>{errors}</strong></p>
    <br>
    <p style='font-size:13px;color:#aaa'>All {saved} invoices are now in PostgreSQL!</p>
    <br>
    <a href='/dashboard' style='display:inline-block;padding:13px 28px;background:#1A5EA8;
       color:#fff;text-decoration:none;border-radius:10px;font-size:15px;font-weight:600'>
       Open Dashboard →</a>"""
    return HTMLResponse(_page("Migration complete!", body))


# ── Pages ────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
def home():
    return FileResponse("static/login.html")


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    path = "static/Erp_Final.html"
    if not os.path.exists(path):
        return HTMLResponse("<h2 style='font-family:sans-serif;padding:40px'>Dashboard file missing.</h2>")
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    auth = """<script>
(function(){var t=localStorage.getItem('erp_token'),u=localStorage.getItem('erp_user');
if(!t||!u){window.location.replace('/');return;}
try{window.ERP_USER=JSON.parse(u);window.ERP_TOKEN=t;window.ERP_API_BASE='/api';}
catch(e){localStorage.clear();window.location.replace('/');}})();
</script>"""
    return HTMLResponse(html.replace("<head>", "<head>" + auth, 1))


@app.get("/upload-page", include_in_schema=False)
def upload_page():
    return FileResponse("static/upload.html")


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return FileResponse("static/login.html")
