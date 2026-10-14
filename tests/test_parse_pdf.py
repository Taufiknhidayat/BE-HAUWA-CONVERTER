import io

import pdfplumber
import pytest

from app.parsers import PlatformMismatchError, UnknownPlatformError, detect_platform, parse_pdf

from .factories import SAMPLE_PRODUCTS, build_shopee_pdf


def test_detect_platform_from_title_when_logo_is_image():
    assert detect_platform('Daftar Pesanan Per Produk\nUsername: x') == 'shopee'
    assert detect_platform('TikTok Shop order list') == 'tiktok'
    assert detect_platform('faktur biasa') is None


def test_detect_tiktok_from_picking_list_columns():
    assert detect_platform('Picking List\nSeller SKU Qty Order ID') == 'tiktok'


def test_detect_tiktok_without_spaces_in_markers():
    """Varian rapat ('tiktok 9.pdf'): penanda tertulis tanpa spasi."""
    assert detect_platform('Picking List\nProductname SKU SellerSKU Qty OrderID') == 'tiktok'


def test_unknown_document_is_rejected():
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(50, 750, 'Faktur biasa')
    c.save()
    with pdfplumber.open(io.BytesIO(buf.getvalue())) as pdf, pytest.raises(UnknownPlatformError):
        parse_pdf(pdf)


def test_platform_hint_matching_detection_is_silent(sample_pdf):
    doc = parse_pdf(sample_pdf, 'shopee')
    assert doc.platform == 'shopee'
    assert not any('tidak cocok' in w for w in doc.warnings)


def test_platform_hint_mismatch_is_rejected(sample_pdf):
    with pytest.raises(PlatformMismatchError) as exc:
        parse_pdf(sample_pdf, 'tiktok')
    assert 'Shopee' in str(exc.value) and 'TikTok' in str(exc.value)


def test_platform_hint_used_when_detection_fails():
    raw = build_shopee_pdf(SAMPLE_PRODUCTS, title='Daftar Pengiriman Barang')
    with pdfplumber.open(io.BytesIO(raw)) as pdf, pytest.raises(UnknownPlatformError):
        parse_pdf(pdf)  # tanpa petunjuk: tetap ditolak
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        doc = parse_pdf(pdf, 'shopee')
    assert doc.platform == 'shopee'
    assert len(doc.lines) == 7
    assert any('tidak terdeteksi otomatis' in w for w in doc.warnings)


def test_unknown_platform_hint_is_ignored_like_no_hint(sample_pdf):
    doc = parse_pdf(sample_pdf, 'lazada')
    assert doc.platform == 'shopee'
    assert not any('lazada' in w for w in doc.warnings)
