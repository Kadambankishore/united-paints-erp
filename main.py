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
        wait_for_db()        # Wait until PostgreSQL is ready
        create_tables()      # Create tables
        seed_default_users() # Create login accounts
        print("✅ Startup complete!")
    except Exception as e:
        print(f"⚠️  Startup warning: {e}")
        print("   App will continue - some features may not work until DB is ready")
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

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Connect routers
app.include_router(auth_router.router,   prefix="/api/auth",   tags=["Login & Users"])
app.include_router(data_router.router,   prefix="/api/data",   tags=["Dashboard Data"])
app.include_router(upload_router.router, prefix="/api/upload", tags=["Upload PDFs"])


@app.get("/health")
def health_check():
    """Railway uses this to check if app is running. Must always return 200."""
    return {"status": "ok", "message": "United Paints ERP is running!"}


@app.get("/", include_in_schema=False)
def home():
    return FileResponse("static/login.html")


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    dashboard_path = "static/Erp_Final.html"
    if not os.path.exists(dashboard_path):
        return HTMLResponse("<h1>Dashboard file not found. Please upload Erp_Final.html to static/ folder.</h1>")

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
