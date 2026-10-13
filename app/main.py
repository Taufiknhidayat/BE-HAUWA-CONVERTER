from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import catalog, csv, health, parsing
from .integrations.odoo import OdooError

FRONTEND_DIST = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'


def create_app() -> FastAPI:
    app = FastAPI(title='PDF → Sales Order Converter')

    @app.exception_handler(OdooError)
    async def odoo_error_handler(_request, exc: OdooError):
        return JSONResponse(status_code=502, content={'detail': str(exc)})

    for module in (health, parsing, catalog, csv):
        app.include_router(module.router)

    # Produksi: sajikan hasil build frontend dari proses yang sama.
    if FRONTEND_DIST.exists():
        app.mount('/', StaticFiles(directory=FRONTEND_DIST, html=True), name='frontend')
    return app


app = create_app()
