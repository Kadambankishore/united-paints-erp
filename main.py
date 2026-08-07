# main.py — United Paints ERP — Phase 2 LIVE DASHBOARD
import os, json, re
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, text
from datetime import datetime

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


def pn(val) -> float:
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
def health(): return {"status": "ok", "message": "United Paints ERP is running!"}


# ── Setup ─────────────────────────────────────────────────────────
@app.get("/setup")
def setup():
    results = []
    try: wait_for_db(max_retries=5, delay=2); results.append("✅ Database connected!")
    except Exception as e: return HTMLResponse(_page("Error", f"<p style='color:#f66'>{e}</p>"), 500)
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
    def fy(m, y): return f"{y}-{str(int(y)+1)[2:]}" if int(m)>=4 else f"{int(y)-1}-{str(y)[2:]}"
    db = SessionLocal(); saved = skipped = errors = 0
    try:
        for inv in bills:
            if inv.get("_is_inter_company") or inv.get("_is_rent"):
                skipped += 1; continue
            c,n,y,m = str(inv.get("company","")),str(inv.get("inv_no","")),str(inv.get("year","2026")),str(inv.get("month","04"))
            if db.query(Invoice).filter(Invoice.company==c,Invoice.inv_no==n,Invoice.year==y).first():
                skipped += 1; continue
            try:
                i = Invoice(company=c,inv_no=n,inv_date=str(inv.get("inv_date",""))[:20],month=m,year=y,
                    month_label=str(inv.get("month_label",""))[:20],financial_year=fy(m,y),
                    buyer_name=str(inv.get("buyer_name",""))[:300],party_uid=str(inv.get("party_uid",""))[:100],
                    place=str(inv.get("place",""))[:150],rep_name=str(inv.get("rep_name","Direct Order"))[:100],
                    area_code=str(inv.get("area_code",""))[:20],grand_total=pn(inv.get("grand_total")),
                    taxable_value=pn(inv.get("taxable_value")),cgst=pn(inv.get("cgst")),
                    sgst=pn(inv.get("sgst")),igst=pn(inv.get("igst")),
                    irn=str(inv.get("irn",""))[:200],source_pdf=str(inv.get("source_pdf",""))[:300],
                    pdf_page=int(pn(inv.get("pdf_page",0))))
                db.add(i); db.flush()
                for p in inv.get("products",[]):
                    db.add(InvoiceLineItem(invoice_id=i.id,company=c,financial_year=fy(m,y),
                        month_label=str(inv.get("month_label",""))[:20],inv_date=str(inv.get("inv_date",""))[:20],
                        rep_name=str(inv.get("rep_name","Direct Order"))[:100],party_uid=str(inv.get("party_uid",""))[:100],
                        buyer_name=str(inv.get("buyer_name",""))[:300],place=str(inv.get("place",""))[:150],
                        product=str(p.get("product",""))[:400],packing=str(p.get("packing",""))[:100],
                        quantity_raw=str(p.get("quantity",""))[:50],items=pn(p.get("items")),
                        rate=pn(p.get("rate")),amount=pn(p.get("amount")),
                        hsn=str(p.get("hsn",""))[:20],gst_pct=str(p.get("gst_pct",""))[:10]))
                saved += 1
                if saved % 200 == 0: db.commit()
            except Exception: errors += 1; db.rollback()
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
    try:
        from database import SessionLocal
        from models import Invoice
        db = SessionLocal()
        dupes = db.execute(text("""
            SELECT company, inv_no, year, COUNT(*) as cnt, MIN(id) as keep_id
            FROM invoices GROUP BY company, inv_no, year HAVING COUNT(*) > 1
        """)).fetchall()
        removed = 0
        for row in dupes:
            to_del = db.query(Invoice).filter(Invoice.company==row[0],Invoice.inv_no==row[1],Invoice.year==row[2],Invoice.id!=row[4]).all()
            for inv in to_del: db.delete(inv); removed += 1
        db.commit()
        total = db.query(Invoice).count()
        months = db.execute(text("""SELECT month_label,company,month,year,COUNT(*) as cnt FROM invoices
            GROUP BY month_label,company,month,year ORDER BY year,month,company""")).fetchall()
        db.close()
        rows = "".join(f"<tr><td style='padding:6px 12px;color:#4A9EE0'>{r[0]}</td><td style='padding:6px 12px'>{r[1]}</td><td style='padding:6px 12px;color:#4ade80;text-align:center'>{r[4]}</td></tr>" for r in months)
        body = f"<p style='font-size:18px;color:#4ade80;margin:8px 0'>✅ Removed <strong>{removed}</strong> duplicates</p><p style='font-size:18px;margin:8px 0'>📊 Total: <strong style='color:#4ade80'>{total:,}</strong></p><table style='width:100%;border-collapse:collapse;font-size:13px;margin:16px 0;text-align:left'><tr style='background:#111d33'><th style='padding:8px 12px;color:#aaa'>Month</th><th style='padding:8px 12px;color:#aaa'>Co</th><th style='padding:8px 12px;text-align:center;color:#aaa'>Count</th></tr>{rows}</table><a href='/verify' style='color:#4A9EE0'>→ Verify</a>&nbsp;&nbsp;<a href='/dashboard' style='color:#4A9EE0'>→ Dashboard</a>"
        return HTMLResponse(_page("Done!", body))
    except Exception as e: return HTMLResponse(_page("Error", f"<p style='color:#f66'>{e}</p>"), 500)


# ── Clean Aug Fakes ───────────────────────────────────────────────
@app.get("/clean-aug")
def clean_aug():
    try:
        from database import SessionLocal
        from models import Invoice
        db = SessionLocal()
        fake = db.query(Invoice).filter(Invoice.month_label.like("Aug-%"),Invoice.inv_no.op("~")(r"^P\d+$")).all()
        removed = len(fake)
        for inv in fake: db.delete(inv)
        db.commit()
        total = db.query(Invoice).count()
        uc = db.query(Invoice).filter(Invoice.month_label.like("Aug-%"),Invoice.company=="UC").count()
        up = db.query(Invoice).filter(Invoice.month_label.like("Aug-%"),Invoice.company=="UP").count()
        db.close()
        body = f"<p style='font-size:18px;color:#4ade80'>✅ Removed <strong>{removed}</strong> fake invoices</p><p style='font-size:18px'>Total: <strong style='color:#4ade80'>{total:,}</strong></p><div style='display:flex;gap:16px;justify-content:center;margin:16px 0'><div style='background:#0d1829;border-radius:10px;padding:16px 24px'><div style='font-size:12px;color:#aaa'>Aug UC</div><div style='font-size:28px;color:#4ade80;font-weight:500'>{uc}</div></div><div style='background:#0d1829;border-radius:10px;padding:16px 24px'><div style='font-size:12px;color:#aaa'>Aug UP</div><div style='font-size:28px;color:#4ade80;font-weight:500'>{up}</div></div></div><br><a href='/verify' style='color:#4A9EE0'>→ Verify</a>"
        return HTMLResponse(_page("Aug Cleaned!", body))
    except Exception as e: return HTMLResponse(_page("Error", f"<p style='color:#f66'>{e}</p>"), 500)


# ── Verify ────────────────────────────────────────────────────────
@app.get("/verify")
def verify():
    try:
        from database import SessionLocal
        from models import Invoice
        db = SessionLocal()
        total = db.query(Invoice).count()
        by_co = db.execute(text("SELECT company,COUNT(*) as cnt,SUM(grand_total) as rev FROM invoices GROUP BY company")).fetchall()
        by_m  = db.execute(text("SELECT month_label,company,month,year,COUNT(*) as cnt,SUM(grand_total) as rev FROM invoices GROUP BY month_label,company,month,year ORDER BY year,month,company")).fetchall()
        by_r  = db.execute(text("SELECT rep_name,COUNT(*) as cnt,SUM(grand_total) as rev FROM invoices GROUP BY rep_name ORDER BY rev DESC LIMIT 15")).fetchall()
        db.close()
        cc = "".join(f"<div style='background:#1a2744;border-radius:10px;padding:18px 24px;text-align:center;flex:1'><div style='font-size:13px;color:#aaa;margin-bottom:6px'>{r[0]} — {'United Chemicals' if r[0]=='UC' else 'United Paints'}</div><div style='font-size:28px;font-weight:500;color:#4ade80'>{r[1]:,}</div><div style='font-size:13px;color:#aaa'>invoices</div><div style='font-size:18px;font-weight:500;color:#fbbf24;margin-top:8px'>₹{round((r[2] or 0)/10000000,2):,} Cr</div></div>" for r in by_co)
        mr = "".join(f"<tr><td style='padding:7px 12px;border-bottom:1px solid #1e2d47;color:#4A9EE0'>{r[0]}</td><td style='padding:7px 12px;border-bottom:1px solid #1e2d47'>{r[1]}</td><td style='padding:7px 12px;border-bottom:1px solid #1e2d47;color:#4ade80;text-align:center'>{r[4]}</td><td style='padding:7px 12px;border-bottom:1px solid #1e2d47;color:#fbbf24;text-align:right'>₹{round((r[5] or 0)/100000,2):,}L</td></tr>" for r in by_m)
        rr = "".join(f"<tr><td style='padding:7px 12px;border-bottom:1px solid #1e2d47;color:#4A9EE0'>{r[0] or 'Direct Order'}</td><td style='padding:7px 12px;border-bottom:1px solid #1e2d47;color:#4ade80;text-align:center'>{r[1]}</td><td style='padding:7px 12px;border-bottom:1px solid #1e2d47;color:#fbbf24;text-align:right'>₹{round((r[2] or 0)/100000,2):,}L</td></tr>" for r in by_r)
        html = f"""<!DOCTYPE html><html><head><title>ERP Verification</title><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style='font-family:-apple-system,sans-serif;background:#0A1628;color:#fff;margin:0;padding:20px'>
<div style='max-width:820px;margin:0 auto'>
  <div style='text-align:center;margin-bottom:24px'><div style='font-size:36px'>🏭</div><h1 style='margin:8px 0 4px'>United Paints ERP</h1><h2 style='color:#4A9EE0;font-weight:400;font-size:18px;margin:0'>Live Database Verification</h2></div>
  <div style='background:#1a2744;border-radius:12px;padding:20px 24px;text-align:center;margin-bottom:16px'><div style='font-size:13px;color:#aaa;margin-bottom:6px'>TOTAL INVOICES IN DATABASE</div><div style='font-size:52px;font-weight:500;color:#4ade80'>{total:,}</div><div style='font-size:13px;color:#aaa;margin-top:4px'>✅ All data is safe in PostgreSQL</div></div>
  <div style='display:flex;gap:14px;margin-bottom:16px'>{cc}</div>
  <div style='background:#0d1829;border-radius:12px;overflow:hidden;margin-bottom:16px'><div style='padding:12px 16px;background:#1a2744;font-size:14px;font-weight:500'>📅 Month-wise Breakdown</div><table style='width:100%;border-collapse:collapse;font-size:13px'><thead><tr style='background:#111d33'><th style='padding:8px 12px;text-align:left;color:#aaa'>Month</th><th style='padding:8px 12px;text-align:left;color:#aaa'>Company</th><th style='padding:8px 12px;text-align:center;color:#aaa'>Invoices</th><th style='padding:8px 12px;text-align:right;color:#aaa'>Revenue</th></tr></thead><tbody>{mr}</tbody></table></div>
  <div style='background:#0d1829;border-radius:12px;overflow:hidden;margin-bottom:16px'><div style='padding:12px 16px;background:#1a2744;font-size:14px;font-weight:500'>👥 Rep-wise Summary</div><table style='width:100%;border-collapse:collapse;font-size:13px'><thead><tr style='background:#111d33'><th style='padding:8px 12px;text-align:left;color:#aaa'>Rep</th><th style='padding:8px 12px;text-align:center;color:#aaa'>Invoices</th><th style='padding:8px 12px;text-align:right;color:#aaa'>Revenue</th></tr></thead><tbody>{rr}</tbody></table></div>
  <div style='text-align:center;padding:12px;font-size:13px;color:#aaa'><a href='/fix-duplicates' style='color:#f87171;text-decoration:none;margin-right:20px'>🔧 Fix Duplicates</a><a href='/dashboard' style='color:#4A9EE0;text-decoration:none;margin-right:20px'>→ Dashboard</a><a href='/upload-page' style='color:#4A9EE0;text-decoration:none'>→ Upload</a></div>
</div></body></html>"""
        return HTMLResponse(html)
    except Exception as e: return HTMLResponse(_page("Error", f"<p style='color:#f66'>{e}</p>"), 500)


# ════════════════════════════════════════════════════════════════════
#  PHASE 2: LIVE DASHBOARD — injects fresh PostgreSQL data into HTML
# ════════════════════════════════════════════════════════════════════
def _build_live_bills():
    """
    Fetch all invoices from PostgreSQL and return:
    - bills_json: JSON string of BILLS array (dashboard format)
    - extra_month_js: JS code for months beyond Jul-2026
    - months_js: updated MONTHS and MONTHS_PROD const declarations
    - data_label: string like 'Apr–Aug 2026'
    - inv_count: total invoice count
    """
    from database import SessionLocal
    from models import Invoice, InvoiceLineItem
    from sqlalchemy.orm import joinedload

    db = SessionLocal()
    try:
        # Fetch ALL invoices for FY 2026-27 with their line items
        invoices = db.query(Invoice).filter(
            Invoice.financial_year == "2026-27"
        ).options(
            joinedload(Invoice.line_items)
        ).order_by(Invoice.year, Invoice.month, Invoice.id).all()

        bills = []
        for inv in invoices:
            bills.append({
                "company":       inv.company,
                "source_pdf":    inv.source_pdf or "",
                "pdf_page":      inv.pdf_page or 0,
                "month_label":   inv.month_label,
                "inv_no":        inv.inv_no,
                "inv_date":      inv.inv_date,
                "month":         inv.month,
                "year":          inv.year,
                "irn":           inv.irn or "",
                "buyer_name":    inv.buyer_name,
                "party_uid":     inv.party_uid,
                "place":         inv.place or "",
                "rep_name":      inv.rep_name or "Direct Order",
                "area_code":     inv.area_code or "",
                "grand_total":   round(inv.grand_total or 0, 2),
                "taxable_value": round(inv.taxable_value or 0, 2),
                "cgst":          round(inv.cgst or 0, 2),
                "sgst":          round(inv.sgst or 0, 2),
                "igst":          round(inv.igst or 0, 2),
                "products": [
                    {
                        "product":  li.product or "",
                        "packing":  li.packing or "",
                        "quantity": li.quantity_raw or "",
                        "items":    li.quantity_raw or "",
                        "rate":     round(li.rate or 0, 2),
                        "amount":   round(li.amount or 0, 2),
                        "hsn":      li.hsn or "",
                        "gst_pct":  li.gst_pct or ""
                    }
                    for li in inv.line_items
                ]
            })

        # Find which months exist beyond Jul-2026 (the original 4 months)
        original = {("04","2026"), ("05","2026"), ("06","2026"), ("07","2026")}
        all_months = {}  # (year,month) -> (label,short)
        for inv in invoices:
            key = (inv.year, inv.month)
            if key not in all_months:
                all_months[key] = inv.month_label

        # Month labels in order
        ordered_months = sorted(all_months.items(), key=lambda x: (x[0][0], x[0][1]))
        month_labels_ordered = [(k, v) for k, v in ordered_months]

        # Build label for header: "Apr–Aug 2026"
        if month_labels_ordered:
            first_lbl = month_labels_ordered[0][1].split("-")[0]  # "Apr"
            last_lbl  = month_labels_ordered[-1][1].split("-")[0]  # "Aug"
            last_year = month_labels_ordered[-1][1].split("-")[1]  # "2026"
            data_label = f"{first_lbl}–{last_lbl} {last_year}"
        else:
            data_label = "Apr–Jul 2026"

        # Extra month JS (months beyond Jul 2026)
        extra_months = []
        months_entries     = []
        months_prod_entries = []

        for (yr, mo), label in ordered_months:
            short = label.split("-")[0]  # "Apr", "May", ... "Aug"
            var = short.upper()          # "APR", "MAY", ... "AUG"

            months_entries.append(
                f"    {{code:'{mo}', key:'{short.lower()}', label:'{short}', data:{var}_PROD}}"
            )
            months_prod_entries.append(
                f"    {{code:'{mo}', label:'{short}', data:{var}_PROD}}"
            )

            if (mo, yr) not in original:
                # This is a new month not in original HTML
                extra_months.append(
                    f"const {var} = DATA.filter(b => getM(b.inv_date) === '{mo}' && getY(b.inv_date) === '{yr}');"
                )
                extra_months.append(
                    f"const {var}_PROD = PROD_DATA.filter(b => getM(b.inv_date)==='{mo}' && getY(b.inv_date)==='{yr}');"
                )

        extra_month_js = "\n".join(extra_months)
        months_js = (
            "const MONTHS = [\n"
            + ",\n".join(months_entries)
            + "\n];"
        )
        months_prod_js = (
            "const MONTHS_PROD = [\n"
            + ",\n".join(months_prod_entries)
            + "\n];"
        )

        return {
            "bills_json":   json.dumps(bills, ensure_ascii=False, separators=(',', ':')),
            "extra_months": extra_month_js,
            "months_js":    months_js,
            "months_prod_js": months_prod_js,
            "data_label":   data_label,
            "inv_count":    len(bills),
        }

    finally:
        db.close()


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    path = "static/Erp_Final.html"
    if not os.path.exists(path):
        return HTMLResponse("<h2 style='font-family:sans-serif;padding:40px'>Dashboard file missing.</h2>")

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Auth check — injected into <head>
    auth = """<script>
(function(){
  var t=localStorage.getItem('erp_token'),u=localStorage.getItem('erp_user');
  if(!t||!u){window.location.replace('/');return;}
  try{window.ERP_USER=JSON.parse(u);window.ERP_TOKEN=t;window.ERP_API_BASE='/api';}
  catch(e){localStorage.clear();window.location.replace('/');}
})();
</script>"""

    # Try to inject live PostgreSQL data
    live = None
    try:
        live = _build_live_bills()
        print(f"✅ Phase 2: Serving live dashboard — {live['inv_count']} invoices, {live['data_label']}")
    except Exception as e:
        print(f"⚠️ Phase 2 fallback to hardcoded data: {e}")

    # Patch the HTML line by line
    result = []
    head_done  = False
    bills_done = False
    aug_done   = False   # extra months injected after JUL_PROD
    months_done = False  # MONTHS replaced
    months_prod_done = False  # MONTHS_PROD replaced

    for i, line in enumerate(lines):
        s = line.strip()

        # 1. Inject auth into <head>
        if not head_done and '<head>' in line:
            line = line.replace('<head>', '<head>' + auth, 1)
            head_done = True

        if live:
            # 2. Replace the BILLS line with live data
            if not bills_done and s.startswith('const BILLS=['):
                ts = datetime.now().strftime('%d-%b-%Y %H:%M')
                line = (f"/* ══ LIVE DATA FROM POSTGRESQL — {live['inv_count']} invoices"
                        f" — {live['data_label']} — Generated {ts} ══ */\n"
                        f"const BILLS={live['bills_json']};\n")
                bills_done = True

            # 3. Inject new month variables right after JUL_PROD line
            elif (not aug_done and live['extra_months']
                  and "const JUL_PROD = PROD_DATA" in s):
                line = line + live['extra_months'] + "\n"
                aug_done = True

            # 4. Replace MONTHS array (lines 931-936)
            elif not months_done and s == 'const MONTHS = [':
                # Skip lines until closing ];
                result.append(live['months_js'] + "\n")
                months_done = True
                # consume until we hit ];
                j = i + 1
                while j < len(lines) and lines[j].strip() != '];':
                    j += 1
                # skip the ]; line too
                lines = lines[:i+1] + lines[j+1:]
                continue

            # 5. Replace MONTHS_PROD array (lines 937-940)
            elif not months_prod_done and s == 'const MONTHS_PROD = [':
                result.append(live['months_prod_js'] + "\n")
                months_prod_done = True
                j = i + 1
                while j < len(lines) and lines[j].strip() != '];':
                    j += 1
                lines = lines[:i+1] + lines[j+1:]
                continue

        result.append(line)

    html = "".join(result)
    return HTMLResponse(html)


@app.get("/upload-page", include_in_schema=False)
def upload_page(): return FileResponse("static/upload.html")


@app.get("/", include_in_schema=False)
def home(): return FileResponse("static/login.html")


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return FileResponse("static/login.html")
