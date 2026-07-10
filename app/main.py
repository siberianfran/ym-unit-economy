"""FastAPI app entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from app.config import settings
from app.database import engine, Base
from app import models  # noqa
from app.routes import (
    auth, workspaces, categories,
    settings as settings_route, skus, marketplace, ya_market,
)


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(categories.router)
app.include_router(settings_route.router)
app.include_router(skus.router)
app.include_router(marketplace.router)
app.include_router(ya_market.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name}


STATIC_DIR = Path(__file__).parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        idx = STATIC_DIR / "index.html"
        if idx.exists():
            return FileResponse(idx)
        return {"status": "ok"}
