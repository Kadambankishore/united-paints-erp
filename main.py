# main.py
import os
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


# ---------------------------------------------------------------
# HEALTH CHECK — Railway uses this (must always return 200 fast)
# ---------------------------------------------------------------
@app.get("/health")
def health_check():
    return {"status": "ok", "message": "United Paints ERP is running!"}


# ---------------------------------------------------------------
# SETUP PAGE — Visit this once to create all users in database
# ---------------------------------------------------------------
@app.get("/setup")
def setup_database():
    """
    One-time setup: creates all database tables and default users.
    Visit this URL once if login says 'Username not found'.
    """
    results = []
    try:
        wait_for_db(max_retries=5, delay=2)
        results.append("✅ Database connected!")
    except Exception as e:
        return HTMLResponse(f"""
        <html><body style='font-family:sans-serif;padding:40px;background:#1a1a2e;color:#fff'>
        <h2>❌ Database Connection Failed</h2>
        <p>Error: {e}</p>
        <p>Make sure DATABASE_URL is set in Railway Variables tab.</p>
        </body></html>
        """, status_code=500)

    try:
        create_tables()
        results.append("✅ Database tables created!")
    except Exception as e:
        results.append(f"⚠️ Tables warning: {e}")

    try:
        seed_default_users()
        results.append("✅ All user accounts created!")
    except Exception as e:
        results.append(f"⚠️ Users warning: {e}")

    results_html = "".join(f"<p style='font-size:18px'>{r}</p>" for r in results)

    return HTMLResponse(f"""
    <html>
    <head><title>ERP Setup</title></head>
    <body style='font-family:-apple-system,sans-serif;background:#0A1628;color:#fff;
                 display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0'>
      <div style='background:#1a2744;border-radius:16px;padding:40px 48px;max-width:500px;text-align:center'>
        <div style='font-size:48px;margin-bottom:16px'>🏭</div>
        <h1 style='color:#fff;margin-bottom:8px'>United Paints ERP</h1>
        <h2 style='color:#4A9EE0;margin-bottom:32px;font-weight:400'>Database Setup</h2>
        {results_html}
        <hr style='border-color:#333;margin:28px 0'>
        <h3 style='color:#4A9EE0;margin-bottom:16px'>Login Credentials</h3>
        <table style='width:100%;border-collapse:collapse;font-size:14px;text-align:left'>
          <tr style='border-bottom:1px solid #333'>
            <th style='padding:8px;color:#aaa'>Who</th>
            <th style='padding:8px;color:#aaa'>Username</th>
            <th style='padding:8px;color:#aaa'>Password</th>
          </tr>
          <tr><td style='padding:8px'>Muruga (Admin)</td><td style='padding:8px;color:#4A9EE0'>muruga</td><td style='padding:8px;color:#F5A623'>Admin@2026</td></tr>
          <tr><td style='padding:8px'>Akshai Sir</td><td style='padding:8px;color:#4A9EE0'>akshai_sir</td><td style='padding:8px;color:#F5A623'>Mgmt@2026</td></tr>
          <tr><td style='padding:8px'>Aakhash Sir</td><td style='padding:8px;color:#4A9EE0'>aakhash_sir</td><td style='padding:8px;color:#F5A623'>Mgmt@2026</td></tr>
          <tr><td style='padding:8px'>Ashok Sir</td><td style='padding:8px;color:#4A9EE0'>ashok_sir</td><td style='padding:8px;color:#F5A623'>Mgmt@2026</td></tr>
          <tr><td style='padding:8px'>Vijay</td><td style='padding:8px;color:#4A9EE0'>vijay</td><td style='padding:8px;color:#F5A623'>Rep@2026</td></tr>
          <tr><td style='padding:8px'>U. Kannan</td><td style='padding:8px;color:#4A9EE0'>u_kannan</td><td style='padding:8px;color:#F5A623'>Rep@2026</td></tr>
          <tr><td style='padding:8px'>L. Sreenivasan</td><td style='padding:8px;color:#4A9EE0'>l_sreenivasan</td><td style='padding:8px;color:#F5A623'>Rep@2026</td></tr>
          <tr><td style='padding:8px'>L.S. Covai</td><td style='padding:8px;color:#4A9EE0'>l_sreenivasan_covai</td><td style='padding:8px;color:#F5A623'>Rep@2026</td></tr>
          <tr><td style='padding:8px'>Babu</td><td style='padding:8px;color:#4A9EE0'>babu</td><td style='padding:8px;color:#F5A623'>Rep@2026</td></tr>
          <tr><td style='padding:8px'>T. Dhinakaran</td><td style='padding:8px;color:#4A9EE0'>t_dhinakaran</td><td style='padding:8px;color:#F5A623'>Rep@2026</td></tr>
          <tr><td style='padding:8px'>Deepak</td><td style='padding:8px;color:#4A9EE0'>deepak</td><td style='padding:8px;color:#F5A623'>Rep@2026</td></tr>
        </table>
        <br>
        <a href='/' style='display:inline-block;margin-top:24px;padding:14px 32px;
           background:#1A5EA8;color:#fff;text-decoration:none;border-radius:10px;
           font-size:16px;font-weight:600'>Go to Login Page →</a>
      </div>
    </body>
    </html>
    """)


# ---------------------------------------------------------------
# PAGE ROUTES
# ---------------------------------------------------------------
@app.get("/", include_in_schema=False)
def home():
    return FileResponse("static/login.html")


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    dashboard_path = "static/Erp_Final.html"
    if not os.path.exists(dashboard_path):
        return HTMLResponse("<h1 style='font-family:sans-serif;padding:40px'>Dashboard file not found. Please upload Erp_Final.html to static/ folder.</h1>")

    with open(dashboard_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    auth_injection = """<script>
(function() {
    var token = localStorage.getItem('erp_token');
    var userStr = localStorage.getItem('erp_user');
    if (!token || !userStr) { window.location.replace('/'); return; }
    try {
        window.ERP_USER = JSON.parse(userStr);
        window.ERP_TOKEN = token;
        window.ERP_API_BASE = '/api';
    } catch(e) { localStorage.clear(); window.location.replace('/'); }
})();
</script>"""

    modified_html = html_content.replace("<head>", "<head>" + auth_injection, 1)
    return HTMLResponse(content=modified_html)


@app.get("/upload-page", include_in_schema=False)
def upload_page():
    return FileResponse("static/upload.html")


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return FileResponse("static/login.html")
