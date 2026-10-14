import io
from concurrent.futures import ThreadPoolExecutor

import pdfplumber
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..config import Settings, get_settings
from ..integrations.odoo import OdooGateway
from ..parsers import PARSERS, ParsedDocument, ParseError, parse_pdf
from ..schemas import BatchParseResult, FileFailure, ParseResult
from ..services.customers import MARKETPLACE_CUSTOMER, find_marketplace_customer
from ..services.matching import match_documents, match_lines
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


# Batas batch banyak PDF: 50 file, total 100 MB (tiap file tetap ≤ batas per file).
MAX_BATCH_FILES = 50
MAX_BATCH_BYTES = 100 * 1024 * 1024


def _unified_date(dates: list[str | None]) -> tuple[str | None, str | None]:
    """Samakan tanggal order antar PDF: pakai tanggal yang paling banyak muncul.

    -> (tanggal_terpilih, peringatan_atau_None). Seluruh tanggal sama (kasus
    umum PDF harian) -> tanpa peringatan.
    """
    present = [d for d in dates if d]
    if not present:
        return None, None
    counts: dict[str, int] = {}
    for d in present:
        counts[d] = counts.get(d, 0) + 1
    chosen = max(counts, key=lambda d: (counts[d], d))
    others = sorted({d for d in present if d != chosen})
    if not others:
        return chosen, None
    return chosen, (
        f'Tanggal order disamakan ke {chosen}; '
        f'PDF bertanggal lain: {", ".join(others)}.'
    )


@router.post('/parse-batch', response_model=BatchParseResult)
def parse_batch(
    files: list[UploadFile] = File(...),
    platform: str | None = Form(default=None),
    odoo: OdooGateway = Depends(get_odoo),
    settings: Settings = Depends(get_settings),
):
    """Upload banyak PDF sekaligus (satu platform) -> satu hasil gabungan.

    Tidak atomik: file yang gagal (bukan PDF, terlalu besar, tidak bisa dibaca,
    platform tak dikenali/beda, tidak ada baris terbaca) DILEWATI dan dicatat di
    `failed` beserta alasannya; file yang berhasil tetap diproses. Hanya bila
    TIDAK ADA file yang berhasil, seluruh batch ditolak (422).
    """
    if not files:
        raise HTTPException(422, 'Pilih minimal 1 file PDF.')
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(422, f'Maksimal {MAX_BATCH_FILES} file per upload.')
    platform = platform or None
    if platform and platform not in PARSERS:
        raise HTTPException(400, 'Platform harus "shopee" atau "tiktok".')

    ok: list[tuple[str, ParsedDocument]] = []  # (nama file, dokumen berhasil)
    failed: list[FileFailure] = []
    total = 0
    for file in files:
        name = file.filename or 'file.pdf'
        content = file.file.read()
        total += len(content)
        if total > MAX_BATCH_BYTES:
            raise HTTPException(413, 'Total ukuran file melebihi 100 MB.')
        if not name.lower().endswith('.pdf'):
            failed.append(FileFailure(file=name, error='File harus berformat PDF.'))
            continue
        if len(content) > settings.max_upload_bytes:
            failed.append(FileFailure(
                file=name, error='Ukuran file melebihi maksimal 20 MB.'))
            continue
        try:
            pdf = pdfplumber.open(io.BytesIO(content))
        except Exception:
            failed.append(FileFailure(file=name, error='File tidak bisa dibaca sebagai PDF.'))
            continue
        with pdf:
            try:
                doc = parse_pdf(pdf, platform)
            except ParseError as e:
                failed.append(FileFailure(file=name, error=str(e)))
                continue
        ok.append((name, doc))

    # Samakan platform: yang dipakai pilihan admin, kalau tidak ada pakai
    # platform terbanyak hasil deteksi. File berplatform lain dilewati.
    detected = [doc.platform for _, doc in ok]
    batch_platform = platform or (max(set(detected), key=detected.count) if detected else None)
    kept: list[tuple[str, ParsedDocument]] = []
    for name, doc in ok:
        if doc.platform != batch_platform:
            failed.append(FileFailure(
                file=name,
                error=f'Platform file ini ({doc.platform}) berbeda dari batch ({batch_platform}).'))
        else:
            kept.append((name, doc))
    ok = kept

    if not ok:
        detail = '; '.join(f'{f.file}: {f.error}' for f in failed) or 'tidak ada file.'
        raise HTTPException(422, f'Tidak ada file yang berhasil diproses ({detail}).')
    docs = [doc for _, doc in ok]

    # Lookup Odoo dipakai bersama untuk seluruh dokumen (satu RPC untuk banyak
    # PDF yang produknya beririsan); pencarian customer independen sehingga
    # jalan paralel seperti endpoint tunggal.
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_match = ex.submit(match_documents, docs, odoo)
        fut_cust = ex.submit(odoo.search_customers, 'Marketplace')
        matched = fut_match.result()
        customers = fut_cust.result()

    warnings: list[str] = []
    for (name, _), doc in zip(ok, docs, strict=True):
        warnings.extend(f'[{name}] {w}' for w in doc.warnings)
    seen: set[str] = set(warnings)
    for _, match_warnings in matched:
        for w in match_warnings:
            if w not in seen:
                seen.add(w)
                warnings.append(w)

    order_date, date_warning = _unified_date([doc.date for doc in docs])
    if date_warning:
        warnings.append(date_warning)
    if failed:
        skipped = ', '.join(f.file for f in failed)
        warnings.append(f'{len(failed)} file dilewati: {skipped}.')
    customer = find_marketplace_customer(batch_platform, customers)
    expected = MARKETPLACE_CUSTOMER.get(batch_platform, 'Marketplace - ' + batch_platform)
    if not customer:
        warnings.append(f'Customer "{expected}" tidak ditemukan di Odoo; pilih manual di tabel.')

    lines = []
    for (name, _), (doc_lines, _) in zip(ok, matched, strict=True):
        for ln in doc_lines:
            ln.source_file = name
            lines.append(ln)
    file_names = [name for name, _ in ok]
    return BatchParseResult(
        platform=batch_platform,
        order_ref=next((doc.ref for doc in docs if doc.ref), None),
        order_date=order_date, lines=lines, warnings=warnings, customer=customer,
        files=file_names, file_name=f'gabungan-{len(file_names)}-file',
        failed=failed,
    )
