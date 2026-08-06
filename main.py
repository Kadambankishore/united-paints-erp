# main.py
# This is the MAIN file. FastAPI starts from here.
# Think of it as the front door of our application.

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from database import create_tables, seed_default_users
from routers import auth_router, data_router, upload_router


# ---------------------------------------------------------------
# STARTUP: runs once when server starts
# ---------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 United Paints ERP is starting up...")
    create_tables()          # Create DB tables if they don't exist
    seed_default_users()     # Create login accounts if they don't exist
    print("✅ Startup complete. Server is ready!")
    yield
    print("👋 Server shutting down.")


# ---------------------------------------------------------------
# CREATE THE APP
# ---------------------------------------------------------------
app = FastAPI(
    title="United Paints ERP",
    description="Live Invoice Intelligence for UC & UP | Madurai",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",    # API documentation at /api/docs
    redoc_url=None
)

# Allow the frontend (browser) to call our API
# This is needed because the HTML page calls /api/... endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],     # In production, replace with your actual domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (CSS, JS, images if any)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------------------------------------------------------------
# CONNECT ALL ROUTERS (groups of API endpoints)
# ---------------------------------------------------------------
app.include_router(auth_router.router,   prefix="/api/auth",   tags=["Login & Users"])
app.include_router(data_router.router,   prefix="/api/data",   tags=["Dashboard Data"])
app.include_router(upload_router.router, prefix="/api/upload", tags=["Upload PDFs"])


# ---------------------------------------------------------------
# PAGE ROUTES
# ---------------------------------------------------------------

@app.get("/", include_in_schema=False)
def home():
    """Home page → Login page"""
    return FileResponse("static/login.html")


@app.get("/dashboard", include_in_schema=False)
def dashboard(request: Request):
    """
    Serve the ERP dashboard HTML.
    We inject a small auth-check script at the top so that
    anyone without a valid login gets sent back to the login page.
    """
    with open("static/Erp_Final.html", "r", encoding="utf-8") as f:
        html_content = f.read()

    # This small script runs before anything else in the page:
    # - Checks if user is logged in (has a token in browser storage)
    # - If not logged in → sends to login page
    # - If logged in → sets window.ERP_USER so the page knows who's viewing
    auth_injection = """
<script>
(function() {
    'use strict';
    var token = localStorage.getItem('erp_token');
    var userStr = localStorage.getItem('erp_user');
    if (!token || !userStr) {
        // Not logged in - go to login page
        window.location.replace('/');
        return;
    }
    try {
        window.ERP_USER = JSON.parse(userStr);
        window.ERP_TOKEN = token;
        window.ERP_API_BASE = '/api';
        console.log('✅ Logged in as:', window.ERP_USER.display_name, '| Role:', window.ERP_USER.role);
    } catch(e) {
        localStorage.clear();
        window.location.replace('/');
    }
})();
</script>
"""

    # Inject just after the opening <head> tag
    modified_html = html_content.replace("<head>", "<head>" + auth_injection, 1)

    return HTMLResponse(content=modified_html)


@app.get("/upload-page", include_in_schema=False)
def upload_page():
    """Daily invoice upload page (admin only)"""
    return FileResponse("static/upload.html")


# ---------------------------------------------------------------
# HEALTH CHECK (Railway uses this to know if app is alive)
# ---------------------------------------------------------------
@app.get("/health")
def health_check():
    return {
        "status":  "ok",
        "message": "United Paints ERP is running!",
        "version": "2.0.0"
    }


# ---------------------------------------------------------------
# CATCH-ALL: If any unknown URL is hit, show login page
# ---------------------------------------------------------------
@app.exception_handler(404)
async def not_found(request: Request, exc):
    return FileResponse("static/login.html")
