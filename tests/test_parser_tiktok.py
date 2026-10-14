import io

import pdfplumber

from app.parsers import parse_pdf

from .factories import TIKTOK_PRODUCTS, build_tiktok_pdf


def _lines(pdf_bytes):
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return parse_pdf(pdf).lines


def test_tiktok_lines_and_totals(tiktok_pdf_bytes):
    with pdfplumber.open(io.BytesIO(tiktok_pdf_bytes)) as pdf:
        doc = parse_pdf(pdf)
    assert doc.platform == 'tiktok'
    assert doc.warnings == []  # total qty (12) cocok dengan header dokumen
    assert len(doc.lines) == 12
    first = doc.lines[0]
    assert (first.sku, first.qty, first.order_no) == ('Pashban-L-03', 1.0, '585818319425209790')
    assert first.name == 'HAUWA Safa Pashban - Pashmina Bandana Instan Malay - Hitam, L'
    assert doc.date is not None and doc.date.endswith('-09-01')


def test_tiktok_qty_two_row_uses_two_order_ids(tiktok_pdf_bytes):
    taupe = [ln for ln in _lines(tiktok_pdf_bytes) if ln.sku == 'MEDRAY-4']
    assert [(ln.qty, ln.order_no) for ln in taupe] == [
        (1.0, '585817856053642710'), (1.0, '585820817587340349')]


def test_tiktok_same_order_id_spans_many_items(tiktok_pdf_bytes):
    lines = _lines(tiktok_pdf_bytes)
    shared = [ln.sku for ln in lines if ln.order_no == '585820817587340349']
    assert shared == ['MEDRAY-1', 'MEDRAY-5', 'MEDRAY-4', 'MEDRAY-7']


def test_tiktok_header_total_mismatch_warns():
    pdf = build_tiktok_pdf(
        TIKTOK_PRODUCTS, stats='Order quantity: 8   Product quantity: 16   Item quantity: 99')
    with pdfplumber.open(io.BytesIO(pdf)) as f:
        doc = parse_pdf(f)
    assert any('Total qty terbaca 12' in w for w in doc.warnings)


def test_tiktok_tight_header_without_spaces():
    """Varian rapat ('tiktok 9.pdf'): header 'Productname'/'SellerSKU'/'OrderID'
    menempel jadi satu token, tapi kolom tetap terbaca penuh tanpa fallback."""
    products = [{'name': ['HAUWAM Medina S Sporty -', 'Bergo Instan Melayu'],
                 'rows': [{'var': 'Hitam', 'seller': 'MEDSPORT.g', 'qty': '1',
                           'orders': ['585834842804881214']},
                          {'var': 'Burgundy', 'seller': 'MEDINA.b', 'qty': '1',
                           'orders': ['585834842804881215']}]}]
    pdf = build_tiktok_pdf(
        products, stats='Order quantity: 2   Product quantity: 1   Item quantity: 2',
        tight_header=True)
    with pdfplumber.open(io.BytesIO(pdf)) as f:
        doc = parse_pdf(f)
    assert doc.platform == 'tiktok'
    assert doc.warnings == []  # bukan hasil fallback generik
    assert [(ln.sku, ln.qty, ln.order_no, ln.variant) for ln in doc.lines] == [
        ('MEDSPORT.g', 1.0, '585834842804881214', 'Hitam'),
        ('MEDINA.b', 1.0, '585834842804881215', 'Burgundy'),
    ]
    assert 'Medina' in (doc.lines[0].product_name or '')
