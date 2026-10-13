import io
from concurrent.futures import ThreadPoolExecutor

import pdfplumber
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..config import Settings, get_settings
from ..integrations.odoo import OdooGateway
from ..parsers import PARSERS, ParseError, parse_pdf
from ..schemas import ParseResult
from ..services.customers import MARKETPLACE_CUSTOMER, find_marketplace_customer
from ..services.matching import match_lines
from .deps import get_odoo

router = APIRouter(prefix='/api', tags=['parsing'])


@router.post('/parse', response_model=ParseResult)
def parse(
    file: UploadFile = File(...),
    platform: str | None = Form(default=None),
    odoo: OdooGateway = Depends(get_odoo),
    settings: Settings = Depends(get_settings),
):
    if not (file.filename or '').lower().endswith('.pdf'):
        raise HTTPException(400, 'File harus berformat PDF.')
    platform = platform or None
    if platform and platform not in PARSERS:
        raise HTTPException(400, 'Platform harus "shopee" atau "tiktok".')
    content = file.file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, 'Ukuran file maksimal 20 MB.')
    try:
        pdf = pdfplumber.open(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(400, 'File tidak bisa dibaca sebagai PDF.') from e

    with pdf:
        try:
            doc = parse_pdf(pdf, platform)
        except ParseError as e:
            raise HTTPException(422, str(e)) from e

    # Pencocokan produk dan pencarian customer independen satu sama lain
    # (masing-masing bisa detik bila Odoo lambat) sehingga jalan paralel.
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_match = ex.submit(match_lines, doc, odoo)
        fut_cust = ex.submit(odoo.search_customers, 'Marketplace')
        lines, match_warnings = fut_match.result()
        customers = fut_cust.result()
    warnings = [*doc.warnings, *match_warnings]
    # Customer marketplace dipasang otomatis sesuai platform hasil deteksi.
    customer = find_marketplace_customer(doc.platform, customers)
    expected = MARKETPLACE_CUSTOMER.get(doc.platform, 'Marketplace - ' + doc.platform)
    if not customer:
        warnings.append(f'Customer "{expected}" tidak ditemukan di Odoo; pilih manual di tabel.')
    return ParseResult(
        platform=doc.platform, order_ref=doc.ref, order_date=doc.date,
        lines=lines, warnings=warnings, customer=customer,
    )
