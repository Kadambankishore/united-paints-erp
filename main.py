# main.py — United Paints ERP — Clean version
import os, json, re
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, text

from database import create_tables, seed_default_users, wait_for_db
from routers import auth_router, data_router, upload_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 United Paints ERP starting...")
    try:
        wait_for_db()
        create_tables()
        seed_default_users()
        print("✅ Ready!")
    except Exception as e:
        print(f"⚠️ Startup warning: {e}")
    yield


app = FastAPI(title="United Paints ERP", version="2.0.0",
              lifespan=lifespan, docs_url="/api/docs", redoc_url=None)

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(auth_router.router,   prefix="/api/auth",   tags=["Auth"])
app.include_router(data_router.router,   prefix="/api/data",   tags=["Data"])
app.include_router(upload_router.router, prefix="/api/upload", tags=["Upload"])


def parse_num(val) -> float:
    if val is None or val == '': return 0.0
    try: return float(val)
    except: m = re.match(r'([\d.]+)', str(val).strip()); return float(m.group(1)) if m else 0.0


def _page(title, body):
    return f"""<!DOCTYPE html><html><head><title>{title}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style='font-family:-apple-system,sans-serif;background:#0A1628;color:#fff;
display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:20px'>
<div style='background:#1a2744;border-radius:16px;padding:40px 48px;max-width:700px;
width:100%;text-align:center'>
<div style='font-size:48px;margin-bottom:12px'>🏭</div>
<h1 style='color:#fff;margin-bottom:6px'>United Paints ERP</h1>
<h2 style='color:#4A9EE0;margin-bottom:28px;font-weight:400'>{title}</h2>
{body}</div></body></html>"""


# ── Health ────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "message": "United Paints ERP is running!"}


# ── Setup ─────────────────────────────────────────────────────────
@app.get("/setup")
def setup():
    results = []
    try:
        wait_for_db(max_retries=5, delay=2); results.append("✅ Database connected!")
    except Exception as e:
        return HTMLResponse(_page("Error", f"<p style='color:#f66'>{e}</p>"), 500)
    try: create_tables();       results.append("✅ Tables ready!")
    except Exception as e:      results.append(f"⚠️ {e}")
    try: seed_default_users();  results.append("✅ Users created!")
    except Exception as e:      results.append(f"⚠️ {e}")
    body = "".join(f"<p style='font-size:17px;margin:8px 0'>{r}</p>" for r in results)
    body += "<br><a href='/migrate' style='color:#4A9EE0'>→ Load invoice data</a>"
    return HTMLResponse(_page("Setup done", body))


# ── Migrate HTML → DB ─────────────────────────────────────────────
@app.get("/migrate")
def migrate():
    html_path = "static/Erp_Final.html"
    if not os.path.exists(html_path):
        return HTMLResponse(_page("File missing", "<p>Erp_Final.html not found.</p>"), 404)
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        bills_json = ""
        for line in lines:
            if line.strip().startswith("const BILLS=["):
                bills_json = re.sub(r"^const BILLS=", "", line.strip()).rstrip(";")
                break
        bills = json.loads(bills_json)
    except Exception as e:
        return HTMLResponse(_page("Read error", f"<p>{e}</p>"), 500)

    from database import SessionLocal
    from models import Invoice, InvoiceLineItem

    def fy(m, y):
        return f"{y}-{str(int(y)+1)[2:]}" if int(m) >= 4 else f"{int(y)-1}-{str(y)[2:]}"

    db = SessionLocal(); saved = skipped = errors = 0
    try:
        for inv in bills:
            if inv.get("_is_inter_company") or inv.get("_is_rent"):
                skipped += 1; continue
            c, n, y, m = str(inv.get("company","")), str(inv.get("inv_no","")), str(inv.get("year","2026")), str(inv.get("month","04"))
            if db.query(Invoice).filter(Invoice.company==c,Invoice.inv_no==n,Invoice.year==y).first():
                skipped += 1; continue
            try:
                i = Invoice(company=c,inv_no=n,inv_date=str(inv.get("inv_date",""))[:20],
                    month=m,year=y,month_label=str(inv.get("month_label",""))[:20],
                    financial_year=fy(m,y),buyer_name=str(inv.get("buyer_name",""))[:300],
                    party_uid=str(inv.get("party_uid",""))[:100],place=str(inv.get("place",""))[:150],
                    rep_name=str(inv.get("rep_name","Direct Order"))[:100],area_code=str(inv.get("area_code",""))[:20],
                    grand_total=parse_num(inv.get("grand_total")),taxable_value=parse_num(inv.get("taxable_value")),
                    cgst=parse_num(inv.get("cgst")),sgst=parse_num(inv.get("sgst")),igst=parse_num(inv.get("igst")),
                    irn=str(inv.get("irn",""))[:200],source_pdf=str(inv.get("source_pdf",""))[:300],
                    pdf_page=int(parse_num(inv.get("pdf_page",0))))
                db.add(i); db.flush()
                for p in inv.get("products",[]):
                    db.add(InvoiceLineItem(invoice_id=i.id,company=c,financial_year=fy(m,y),
                        month_label=str(inv.get("month_label",""))[:20],inv_date=str(inv.get("inv_date",""))[:20],
                        rep_name=str(inv.get("rep_name","Direct Order"))[:100],party_uid=str(inv.get("party_uid",""))[:100],
                        buyer_name=str(inv.get("buyer_name",""))[:300],place=str(inv.get("place",""))[:150],
                        product=str(p.get("product",""))[:400],packing=str(p.get("packing",""))[:100],
                        quantity_raw=str(p.get("quantity",""))[:50],items=parse_num(p.get("items")),
                        rate=parse_num(p.get("rate")),amount=parse_num(p.get("amount")),
                        hsn=str(p.get("hsn",""))[:20],gst_pct=str(p.get("gst_pct",""))[:10]))
                saved += 1
                if saved % 200 == 0: db.commit()
            except Exception as e: errors += 1; db.rollback()
        db.commit()
    finally: db.close()
    body = f"""<p style='font-size:18px;margin:8px 0'>✅ Saved: <strong>{saved}</strong></p>
    <p style='font-size:18px;margin:8px 0'>⏭️ Skipped: <strong>{skipped}</strong></p>
    <p style='font-size:18px;margin:8px 0'>❌ Errors: <strong>{errors}</strong></p>
    <br><a href='/dashboard' style='display:inline-block;padding:13px 28px;background:#1A5EA8;
    color:#fff;text-decoration:none;border-radius:10px;font-size:15px;font-weight:600'>Open Dashboard →</a>"""
    return HTMLResponse(_page("Migration complete!", body))


# ── Fix Duplicates ────────────────────────────────────────────────
@app.get("/fix-duplicates")
def fix_duplicates():
    """Removes duplicate invoices. Safe to run multiple times."""
    try:
        from database import SessionLocal
        from models import Invoice

        db = SessionLocal()
        # Find groups with more than 1 invoice for same company+inv_no+year
        dupes = db.execute(text("""
            SELECT company, inv_no, year, COUNT(*) as cnt, MIN(id) as keep_id
            FROM invoices
            GROUP BY company, inv_no, year
            HAVING COUNT(*) > 1
        """)).fetchall()

        removed = 0
        for row in dupes:
            to_delete = db.query(Invoice).filter(
                Invoice.company == row[0],
                Invoice.inv_no  == row[1],
                Invoice.year    == row[2],
                Invoice.id      != row[4]
            ).all()
            for inv in to_delete:
                db.delete(inv)
                removed += 1

        db.commit()
        total = db.query(Invoice).count()

        # Month breakdown — include year and month in GROUP BY so PostgreSQL is happy
        months = db.execute(text("""
            SELECT month_label, company, month, year, COUNT(*) as cnt
            FROM invoices
            GROUP BY month_label, company, month, year
            ORDER BY year, month, company
        """)).fetchall()
        db.close()

        rows = "".join(
            f"<tr><td style='padding:6px 12px;color:#4A9EE0'>{r[0]}</td>"
            f"<td style='padding:6px 12px;color:#fff'>{r[1]}</td>"
            f"<td style='padding:6px 12px;color:#4ade80;text-align:center'>{r[4]}</td></tr>"
            for r in months
        )
        body = f"""
        <p style='font-size:18px;color:#4ade80;margin:8px 0'>✅ Removed <strong>{removed}</strong> duplicates</p>
        <p style='font-size:18px;margin:8px 0'>📊 Clean total: <strong style='color:#4ade80'>{total:,}</strong> invoices</p>
        <table style='width:100%;border-collapse:collapse;font-size:13px;margin:16px 0;text-align:left'>
          <tr style='background:#111d33'>
            <th style='padding:8px 12px;color:#aaa'>Month</th>
            <th style='padding:8px 12px;color:#aaa'>Company</th>
            <th style='padding:8px 12px;text-align:center;color:#aaa'>Invoices</th>
          </tr>{rows}
        </table>
        <a href='/verify' style='color:#4A9EE0'>→ Full verify</a>&nbsp;&nbsp;
        <a href='/dashboard' style='color:#4A9EE0'>→ Dashboard</a>"""
        return HTMLResponse(_page("Duplicates Fixed!", body))
    except Exception as e:
        return HTMLResponse(_page("Error", f"<p style='color:#f66'>{e}</p>"), 500)


# ── Verify ────────────────────────────────────────────────────────
@app.get("/verify")
def verify():
    try:
        from database import SessionLocal
        from models import Invoice

        db = SessionLocal()
        total = db.query(Invoice).count()

        by_company = db.execute(text("""
            SELECT company, COUNT(*) as cnt, SUM(grand_total) as rev
            FROM invoices GROUP BY company
        """)).fetchall()

        by_month = db.execute(text("""
            SELECT month_label, company, month, year, COUNT(*) as cnt, SUM(grand_total) as rev
            FROM invoices
            GROUP BY month_label, company, month, year
            ORDER BY year, month, company
        """)).fetchall()

        by_rep = db.execute(text("""
            SELECT rep_name, COUNT(*) as cnt, SUM(grand_total) as rev
            FROM invoices GROUP BY rep_name
            ORDER BY rev DESC LIMIT 15
        """)).fetchall()
        db.close()

        company_cards = "".join(
            f"<div style='background:#1a2744;border-radius:10px;padding:18px 24px;text-align:center;flex:1'>"
            f"<div style='font-size:13px;color:#aaa;margin-bottom:6px'>{r[0]} — {'United Chemicals' if r[0]=='UC' else 'United Paints'}</div>"
            f"<div style='font-size:28px;font-weight:500;color:#4ade80'>{r[1]:,}</div>"
            f"<div style='font-size:13px;color:#aaa;margin-top:4px'>invoices</div>"
            f"<div style='font-size:18px;font-weight:500;color:#fbbf24;margin-top:8px'>₹{round((r[2] or 0)/10000000,2):,} Cr</div></div>"
            for r in by_company
        )
        month_rows = "".join(
            f"<tr><td style='padding:7px 12px;border-bottom:1px solid #1e2d47;color:#4A9EE0'>{r[0]}</td>"
            f"<td style='padding:7px 12px;border-bottom:1px solid #1e2d47'>{r[1]}</td>"
            f"<td style='padding:7px 12px;border-bottom:1px solid #1e2d47;color:#4ade80;text-align:center'>{r[4]}</td>"
            f"<td style='padding:7px 12px;border-bottom:1px solid #1e2d47;color:#fbbf24;text-align:right'>₹{round((r[5] or 0)/100000,2):,}L</td></tr>"
            for r in by_month
        )
        rep_rows = "".join(
            f"<tr><td style='padding:7px 12px;border-bottom:1px solid #1e2d47;color:#4A9EE0'>{r[0] or 'Direct Order'}</td>"
            f"<td style='padding:7px 12px;border-bottom:1px solid #1e2d47;color:#4ade80;text-align:center'>{r[1]}</td>"
            f"<td style='padding:7px 12px;border-bottom:1px solid #1e2d47;color:#fbbf24;text-align:right'>₹{round((r[2] or 0)/100000,2):,}L</td></tr>"
            for r in by_rep
        )

        html = f"""<!DOCTYPE html><html><head><title>ERP Verification</title>
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style='font-family:-apple-system,sans-serif;background:#0A1628;color:#fff;margin:0;padding:20px'>
<div style='max-width:820px;margin:0 auto'>
  <div style='text-align:center;margin-bottom:24px'>
    <div style='font-size:36px'>🏭</div>
    <h1 style='margin:8px 0 4px'>United Paints ERP</h1>
    <h2 style='color:#4A9EE0;font-weight:400;font-size:18px;margin:0'>Live Database Verification</h2>
  </div>
  <div style='background:#1a2744;border-radius:12px;padding:20px 24px;text-align:center;margin-bottom:16px'>
    <div style='font-size:13px;color:#aaa;margin-bottom:6px'>TOTAL INVOICES IN DATABASE</div>
    <div style='font-size:52px;font-weight:500;color:#4ade80'>{total:,}</div>
    <div style='font-size:13px;color:#aaa;margin-top:4px'>✅ All data is safe in PostgreSQL</div>
  </div>
  <div style='display:flex;gap:14px;margin-bottom:16px'>{company_cards}</div>
  <div style='background:#0d1829;border-radius:12px;overflow:hidden;margin-bottom:16px'>
    <div style='padding:12px 16px;background:#1a2744;font-size:14px;font-weight:500'>📅 Month-wise Breakdown</div>
    <table style='width:100%;border-collapse:collapse;font-size:13px'>
      <thead><tr style='background:#111d33'>
        <th style='padding:8px 12px;text-align:left;color:#aaa'>Month</th>
        <th style='padding:8px 12px;text-align:left;color:#aaa'>Company</th>
        <th style='padding:8px 12px;text-align:center;color:#aaa'>Invoices</th>
        <th style='padding:8px 12px;text-align:right;color:#aaa'>Revenue</th>
      </tr></thead>
      <tbody>{month_rows}</tbody>
    </table>
  </div>
  <div style='background:#0d1829;border-radius:12px;overflow:hidden;margin-bottom:16px'>
    <div style='padding:12px 16px;background:#1a2744;font-size:14px;font-weight:500'>👥 Rep-wise Summary</div>
    <table style='width:100%;border-collapse:collapse;font-size:13px'>
      <thead><tr style='background:#111d33'>
        <th style='padding:8px 12px;text-align:left;color:#aaa'>Rep</th>
        <th style='padding:8px 12px;text-align:center;color:#aaa'>Invoices</th>
        <th style='padding:8px 12px;text-align:right;color:#aaa'>Revenue</th>
      </tr></thead>
      <tbody>{rep_rows}</tbody>
    </table>
  </div>
  <div style='text-align:center;padding:12px;font-size:13px;color:#aaa'>
    <a href='/fix-duplicates' style='color:#f87171;text-decoration:none;margin-right:20px'>🔧 Fix Duplicates</a>
    <a href='/dashboard' style='color:#4A9EE0;text-decoration:none;margin-right:20px'>→ Dashboard</a>
    <a href='/upload-page' style='color:#4A9EE0;text-decoration:none'>→ Upload</a>
  </div>
</div></body></html>"""
        return HTMLResponse(html)
    except Exception as e:
        return HTMLResponse(_page("Error", f"<p style='color:#f66'>{e}</p>"), 500)


# ── Pages ─────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
def home(): return FileResponse("static/login.html")

@app.get("/dashboard", include_in_schema=False)
def dashboard():
    path = "static/Erp_Final.html"
    if not os.path.exists(path):
        return HTMLResponse("<h2 style='font-family:sans-serif;padding:40px'>Dashboard file missing.</h2>")
    with open(path, "r", encoding="utf-8") as f: html = f.read()
    auth = """<script>
(function(){var t=localStorage.getItem('erp_token'),u=localStorage.getItem('erp_user');
if(!t||!u){window.location.replace('/');return;}
try{window.ERP_USER=JSON.parse(u);window.ERP_TOKEN=t;window.ERP_API_BASE='/api';}
catch(e){localStorage.clear();window.location.replace('/');}})();
</script>"""
    return HTMLResponse(html.replace("<head>", "<head>" + auth, 1))

@app.get("/upload-page", include_in_schema=False)
def upload_page(): return FileResponse("static/upload.html")

@app.exception_handler(404)
async def not_found(request: Request, exc):
    return FileResponse("static/login.html")
