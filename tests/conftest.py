import io

import pdfplumber
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_odoo
from app.integrations.odoo import MockOdooClient
from app.main import create_app

from .factories import SAMPLE_PRODUCTS, TIKTOK_PRODUCTS, build_shopee_pdf, build_tiktok_pdf


@pytest.fixture(scope='session')
def sample_pdf_bytes() -> bytes:
    return build_shopee_pdf(SAMPLE_PRODUCTS)


@pytest.fixture
def sample_pdf(sample_pdf_bytes):
    with pdfplumber.open(io.BytesIO(sample_pdf_bytes)) as pdf:
        yield pdf


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_odoo] = lambda: MockOdooClient()
    return TestClient(app)


@pytest.fixture(scope='session')
def tiktok_pdf_bytes() -> bytes:
    return build_tiktok_pdf(TIKTOK_PRODUCTS)
