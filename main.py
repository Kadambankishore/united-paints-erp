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
        print("   Visit /setup in browser to initialize database manually.")
    yield
    print("👋 Shutting down.")


app = FastAPI(
    title="United Paints ERP",
    description="Live Invoice Intelligence for UC & UP",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(auth_router.router,   prefix="/api/auth",   tags=["Login & Users"])
app.include_router(data_router.router,   prefix="/api/data",   tags=["Dashboard Data"])
app.include_router(upload_router.router, prefix="/api/upload", tags=["Upload PDFs"])


# ─────────────────────────────────────────────
#  HEALTH CHECK
# ─────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {"status": "ok", "message": "United Paints ERP is running!"}


# ─────────────────────────────────────────────
#  SETUP  (creates tables + users)
# ─────────────────────────────────────────────
@app.get("/setup")
def setup_database():
    results = []
    try:
        wait_for_db(max_retries=5, delay=2)
        results.append("✅ Database connected!")
    except Exception as e:
        return HTMLResponse(_page("❌ DB failed", f"<p style='color:#c00'>{e}</p>"), status_code=500)

    try:
        create_tables();   results.append("✅ Tables ready!")
    except Exception as e: results.append(f"⚠️ Tables: {e}")

    try:
        seed_default_users(); results.append("✅ Users created!")
    except Exception as e:   results.append(f"⚠️ Users: {e}")

    body = "".join(f"<p style='font-size:17px;margin:8px 0'>{r}</p>" for r in results)
    body += "<br><a href='/migrate' style='color:#4A9EE0'>→ Load invoice data next</a>"
    return HTMLResponse(_page("Setup done", body))


# ─────────────────────────────────────────────
#  MIGRATE  (loads Apr-Jul data from Erp_Final.html → PostgreSQL)
# ─────────────────────────────────────────────
@app.get("/migrate")
def migrate_html_data():
    """
    Reads Erp_Final.html, extracts all invoices and loads them into PostgreSQL.
    Run this ONCE after first deployment to populate the database.
    Safe to run again — duplicates are skipped automatically.
    """
    html_path = "static/Erp_Final.html"
    if not os.path.exists(html_path):
        return HTMLResponse(_page("File missing",
            "<p>static/Erp_Final.html not found. Make sure it was pushed to GitHub.</p>"), 404)

    # ── Read BILLS from HTML ──────────────────────────────────────────────
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        bills_json = ""
        for line in lines:
            if line.strip().startswith("const BILLS=["):
                bills_json = line.strip()
                bills_json = re.sub(r"^const BILLS=", "", bills_json).rstrip(";").rstrip()
                break

        if not bills_json:
            return HTMLResponse(_page("Parse error", "<p>Could not find BILLS data in HTML.</p>"), 500)

        bills = json.loads(bills_json)
    except Exception as e:
        return HTMLResponse(_page("Read error", f"<p>{e}</p>"), 500)

    # ── Insert into PostgreSQL ────────────────────────────────────────────
    from database import SessionLocal
    from models import Invoice, InvoiceLineItem

    def get_fy(month, year):
        m = int(month); y = int(year)
        return f"{y}-{str(y+1)[2:]}" if m >= 4 else f"{y-1}-{str(y)[2:]}"

    db = SessionLocal()
    saved = skipped = errors = 0

    try:
        for inv in bills:
            if inv.get("_is_inter_company") or inv.get("_is_rent"):
                skipped += 1; continue

            company = inv.get("company", "")
            inv_no  = str(inv.get("inv_no", ""))
            year    = str(inv.get("year", ""))
            month   = str(inv.get("month", ""))

            exists = db.query(Invoice).filter(
                Invoice.company == company,
                Invoice.inv_no  == inv_no,
                Invoice.year    == year
            ).first()
            if exists:
                skipped += 1; continue

            try:
                fy = get_fy(month, year)
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
                    place          = str(inv.get("place",      ""))[:150],
                    rep_name       = str(inv.get("rep_name", "Direct Order"))[:100],
                    area_code      = str(inv.get("area_code",  ""))[:20],
                    grand_total    = float(inv.get("grand_total",   0) or 0),
                    taxable_value  = float(inv.get("taxable_value", 0) or 0),
                    cgst           = float(inv.get("cgst",  0) or 0),
                    sgst           = float(inv.get("sgst",  0) or 0),
                    igst           = float(inv.get("igst",  0) or 0),
                    irn            = str(inv.get("irn", ""))[:200],
                    source_pdf     = str(inv.get("source_pdf", ""))[:300],
                    pdf_page       = int(inv.get("pdf_page", 0) or 0)
                )
                db.add(invoice)
                db.flush()

                for prod in inv.get("products", []):
                    db.add(InvoiceLineItem(
                        invoice_id     = invoice.id,
                        company        = company,
                        financial_year = fy,
                        month_label    = str(inv.get("month_label", "")),
                        inv_date       = str(inv.get("inv_date",    "")),
                        rep_name       = str(inv.get("rep_name", "Direct Order"))[:100],
                        party_uid      = str(inv.get("party_uid",   ""))[:100],
                        buyer_name     = str(inv.get("buyer_name",  ""))[:300],
                        place          = str(inv.get("place",        ""))[:150],
                        product        = str(prod.get("product",     ""))[:400],
                        packing        = str(prod.get("packing",     ""))[:100],
                        quantity_raw   = str(prod.get("quantity",    ""))[:50],
                        items          = float(prod.get("items",  0) or 0),
                        rate           = float(prod.get("rate",   0) or 0),
                        amount         = float(prod.get("amount", 0) or 0),
                        hsn            = str(prod.get("hsn",      ""))[:20],
                        gst_pct        = str(prod.get("gst_pct",  ""))[:10],
                    ))

                saved += 1
                if saved % 200 == 0:
                    db.commit()

            except Exception as e:
                errors += 1
                db.rollback()

        db.commit()
    finally:
        db.close()

    body = f"""
    <p style='font-size:17px;margin:8px 0'>✅ Invoices saved to database: <strong>{saved}</strong></p>
    <p style='font-size:17px;margin:8px 0'>⏭️  Skipped (duplicates / inter-company): <strong>{skipped}</strong></p>
    <p style='font-size:17px;margin:8px 0'>❌ Errors: <strong>{errors}</strong></p>
    <br>
    <p style='font-size:14px;color:#aaa'>Migration complete! Your PostgreSQL database now has all invoice data.</p>
    <br>
    <a href='/dashboard' style='display:inline-block;padding:13px 28px;background:#1A5EA8;color:#fff;
       text-decoration:none;border-radius:10px;font-size:15px;font-weight:600'>
       Open Dashboard →
    </a>
    """
    return HTMLResponse(_page("Migration complete!", body))


# ─────────────────────────────────────────────
#  PAGE ROUTES
# ─────────────────────────────────────────────
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


# ─────────────────────────────────────────────
#  HELPER: shared page template
# ─────────────────────────────────────────────
def _page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html><html><head><title>{title}</title></head>
<body style='font-family:-apple-system,sans-serif;background:#0A1628;color:#fff;
display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0'>
<div style='background:#1a2744;border-radius:16px;padding:40px 48px;max-width:540px;text-align:center'>
<div style='font-size:48px;margin-bottom:12px'>🏭</div>
<h1 style='color:#fff;margin-bottom:6px'>United Paints ERP</h1>
<h2 style='color:#4A9EE0;margin-bottom:28px;font-weight:400'>{title}</h2>
{body}
</div></body></html>"""
