# FastAPI Application for Fatture Locali & HACCP (Krügel – Lavis & Cafè L’Incontro – Pergine)
import os
import asyncio
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.database import init_db
from backup import create_backup
from app.routes.auth import router as auth_router
from app.routes.users import router as users_router
from app.routes.haccp import router as haccp_router
from app.routes.invoices import router as invoices_router
from app.routes.lines import router as lines_router
from app.routes.analytics import router as analytics_router
from app.routes.unassigned import router as unassigned_router
from app.routes.settings import router as settings_router
from app.routes.demo import router as demo_router

async def schedule_daily_backup():
    """Task asincrono in background per backup automatico notturno (ore 03:00)"""
    while True:
        try:
            now = datetime.now()
            target = now.replace(hour=3, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            await asyncio.sleep(wait_seconds)
            create_backup()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[Backup Automatico] Errore durante il backup pianificato: {e}")
            await asyncio.sleep(3600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    backup_task = asyncio.create_task(schedule_daily_backup())
    yield
    backup_task.cancel()

app = FastAPI(
    title="Fatture Locali & HACCP • Krügel – Lavis & Cafè L’Incontro – Pergine",
    description="Applicazione privata per gestione fatture, controllo prezzi e autocontrollo HACCP",
    version="2.0.0",
    lifespan=lifespan
)

allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
if not allowed_origins:
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Includi Router API
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(haccp_router)
app.include_router(invoices_router)
app.include_router(lines_router)
app.include_router(analytics_router)
app.include_router(unassigned_router)
app.include_router(settings_router)
app.include_router(demo_router)

# Mount dei file statici
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(
            index_path,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return {"message": "Fatture Locali & HACCP attiva. Interfaccia web in caricamento..."}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
