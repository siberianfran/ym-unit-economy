"""FastAPI app entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy import inspect, text

from app.config import settings
from app.database import engine, Base
from app import models  # noqa
from app.routes import (
    auth, workspaces, categories,
    settings as settings_route, skus, marketplace, ya_market, fin_report, ozon,
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


def _apply_lightweight_migrations():
    with engine.begin() as conn:
        insp = inspect(conn)
        try:
            sku_cols = {c["name"] for c in insp.get_columns("skus")}
        except Exception:
            sku_cols = None
        if sku_cols is not None and "stock_total" not in sku_cols:
            try:
                conn.execute(text("ALTER TABLE skus ADD COLUMN stock_total INTEGER DEFAULT 0"))
            except Exception as e:
                print(f"[migrate] add stock_total failed: {e}")
        # Ozon-колонки в store_settings
        try:
            ss_cols = {c["name"] for c in insp.get_columns("store_settings")}
        except Exception:
            ss_cols = None
        if ss_cols is not None:
            for col, ddl in [
                ("ozon_commission_override", "ALTER TABLE store_settings ADD COLUMN ozon_commission_override FLOAT"),
                ("ozon_nonlocal_pct", "ALTER TABLE store_settings ADD COLUMN ozon_nonlocal_pct FLOAT DEFAULT 0"),
                ("ozon_realfbs_carrier_rub", "ALTER TABLE store_settings ADD COLUMN ozon_realfbs_carrier_rub FLOAT DEFAULT 250"),
                ("ozon_fbs_processing_mode", "ALTER TABLE store_settings ADD COLUMN ozon_fbs_processing_mode VARCHAR(16) DEFAULT 'sc_trust'"),
            ]:
                if col not in ss_cols:
                    try:
                        conn.execute(text(ddl))
                    except Exception as e:
                        print(f"[migrate] add {col} failed: {e}")


_apply_lightweight_migrations()


app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(categories.router)
app.include_router(settings_route.router)
app.include_router(skus.router)
app.include_router(marketplace.router)
app.include_router(ya_market.router)
app.include_router(fin_report.router)
app.include_router(ozon.router)


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
