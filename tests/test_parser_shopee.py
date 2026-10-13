import io

import pdfplumber

from app.parsers import parse_pdf

from .factories import build_shopee_pdf, build_shopee_tight_pdf


def test_shopee_one_product_becomes_variant_lines_with_first_order(sample_pdf):
    """Satu produk = satu Sales Order: semua baris varian memakai nomor pesanan
    pertama produk, qty per warna dipertahankan (tidak dibagi-bagi per nomor)."""
    doc = parse_pdf(sample_pdf)
    assert doc.platform == 'shopee'
    assert doc.date == '2026-08-25'
    assert len(doc.lines) == 7
    first = doc.lines[:2]
    assert [(ln.sku, ln.qty, ln.order_no) for ln in first] == [
        ('MED 2.0-6', 1.0, '260831RRGRKTCM'),
        ('MED 2.0-m', 1.0, '260831RRGRKTCM'),
    ]
    assert first[0].name == 'HAUWA Hijab - Medina 2.0 Bergo Tanpa Tali jersey Korea - Maroon,L'
    assert first[0].product_name == 'HAUWA Hijab - Medina 2.0 Bergo Tanpa Tali jersey Korea'


def test_shopee_order_numbers_are_not_split_across_variant_lines(sample_pdf):
    """Produk dengan total qty 3 dan 3 nomor pesanan: variasi tetap satu baris
    (qty agregat), Customer Reference = nomor pertama. Nomor lain tidak dipakai."""
    lines = parse_pdf(sample_pdf).lines[2:4]
    assert [(ln.sku, ln.qty, ln.order_no) for ln in lines] == [
        ('pas-Anak-RAYON-2', 2.0, '260831S2NPGMX8'),
        ('pas-Anak-RAYON-8', 1.0, '260831S2NPGMX8'),
    ]


def test_shopee_extra_order_numbers_kept_as_ref_not_lost(sample_pdf):
    """Kasus dulu 'tidak konsisten' (3 variasi, 2 nomor) kini tetap dibaca lengkap:
    semua varian jadi baris, qty utuh, nomor pertama jadi referensi."""
    doc = parse_pdf(sample_pdf)
    last = doc.lines[4:]
    assert [(ln.sku, ln.qty, ln.order_no) for ln in last] == [
        ('Raya--S--7', 1.0, '260831S2TWFMEP'),
        ('Raya--S--1', 2.0, '260831S2TWFMEP'),
        ('Raya--S--4', 1.0, '260831S2TWFMEP'),
    ]
    assert doc.warnings == []


def test_single_product_layout_with_wrapped_sku():
    products = [{
        'sku': ['Bergo', 'Instan'], 'step': 38,
        'name': ['HAUWA Hijab - Lalisa'],
        'variants': [
            {'kode': ['LALISA.B', 'urg'], 'var': 'Burgundy', 'qty': '1'},
            {'kode': ['LALISA.c'], 'var': 'Nude', 'qty': '1'},
        ],
        'orders': ['2608259Y1VKWJD', '2608259Y2HN2HG'],
    }]
    with pdfplumber.open(io.BytesIO(build_shopee_pdf(products))) as pdf:
        doc = parse_pdf(pdf)
    assert [ln.sku for ln in doc.lines] == ['LALISA.Burg', 'LALISA.c']
    assert doc.warnings == []


def test_wrapped_order_number_is_reconstructed():
    """Nomor pesanan panjang terpotong dua baris di PDF (mis. '260831AAR6J34GNE'
    + 'TFQ'); parser menyusunnya kembali menjadi satu nomor utuh."""
    products = [{
        'sku': ['Bergo', 'Instan'], 'step': 38,
        'name': ['HAUWA Hijab - Lalisa'],
        'variants': [{'kode': ['LALISA.b'], 'var': 'Cream', 'qty': '10'}],
        'orders': [['260831AAR6J34GNE', 'TFQ']],
    }]
    with pdfplumber.open(io.BytesIO(build_shopee_pdf(products))) as pdf:
        doc = parse_pdf(pdf)
    assert [(ln.qty, ln.order_no) for ln in doc.lines] == [(10.0, '260831AAR6J34GNETFQ')]
    assert doc.warnings == []


def test_shopee_download_date_from_top_line():
    """Contoh nyata dari PDF: 'Waktu & Tanggal Download: 09:23 AM 01/09/2026'
    dibaca sebagai DD/MM -> 2026-09-01 (1 September)."""
    products = [{
        'sku': ['Bergo'], 'step': 38,
        'name': ['HAUWA Hijab - Lalisa'],
        'variants': [{'kode': ['LALISA.c'], 'var': 'Nude', 'qty': '1'}],
        'orders': ['2608259Y2HN2HG'],
    }]
    pdf = build_shopee_pdf(products, download='09:23 AM 01/09/2026')
    with pdfplumber.open(io.BytesIO(pdf)) as p:
        assert parse_pdf(p).date == '2026-09-01'


def test_shopee_download_date_tolerates_spacing():
    """Spasi di sekitar titik dua (umum di PDF asli) dan tahun 2 digit tetap dibaca DD/MM."""
    from app.parsers.shopee import _DOWNLOAD_DATE
    m = _DOWNLOAD_DATE.search('Waktu & Tanggal Download : 09:23 AM 01/09/26')
    assert m.groups() == ('01', '09', '26')
    assert not _DOWNLOAD_DATE.search('Dibuat atas Download Pdf.' + 'X' * 60 + ' 01/09/2026')


def _parse_single_product(variants, orders):
    products = [{
        'sku': ['Bergo', 'Instan'], 'step': 38,
        'name': ['HAUWA Hijab - Lalisa'],
        'variants': variants,
        'orders': orders,
    }]
    with pdfplumber.open(io.BytesIO(build_shopee_pdf(products))) as pdf:
        return parse_pdf(pdf)


def test_one_order_number_covers_all_variants_of_the_product():
    # PDF asli: satu pesanan berisi 4 warna, hanya ada satu nomor pesanan.
    doc = _parse_single_product(
        [{'kode': ['LALISA.b'], 'var': 'Cream', 'qty': '1'},
         {'kode': ['LALISA.f'], 'var': 'Tanah', 'qty': '1'},
         {'kode': ['LALISA.g'], 'var': 'Hitam', 'qty': '1'},
         {'kode': ['LALISA.i'], 'var': 'Abu Silver', 'qty': '1'}],
        ['260831SGYKRV6U'],
    )
    assert [(ln.sku, ln.qty, ln.order_no) for ln in doc.lines] == [
        ('LALISA.b', 1.0, '260831SGYKRV6U'),
        ('LALISA.f', 1.0, '260831SGYKRV6U'),
        ('LALISA.g', 1.0, '260831SGYKRV6U'),
        ('LALISA.i', 1.0, '260831SGYKRV6U'),
    ]
    assert doc.warnings == []


def test_one_order_number_keeps_qty_per_color():
    # 1 pembeli: 2 Hitam + 3 Cream, satu nomor pesanan.
    doc = _parse_single_product(
        [{'kode': ['LALISA.g'], 'var': 'Hitam', 'qty': '2'},
         {'kode': ['LALISA.b'], 'var': 'Cream', 'qty': '3'}],
        ['260831SGYKRV6U'],
    )
    assert [(ln.sku, ln.qty, ln.order_no) for ln in doc.lines] == [
        ('LALISA.g', 2.0, '260831SGYKRV6U'),
        ('LALISA.b', 3.0, '260831SGYKRV6U'),
    ]
    assert doc.warnings == []


def test_product_without_readable_order_numbers_warns():
    doc = _parse_single_product(
        [{'kode': ['LALISA.b'], 'var': 'Cream', 'qty': '1'}],
        [],
    )
    assert [(ln.qty, ln.order_no) for ln in doc.lines] == [(1.0, None)]
    assert len(doc.warnings) == 1
    assert 'Lalisa' in doc.warnings[0]


def test_tight_columns_keep_name_variant_and_sku_intact():
    """PDF berkolom rapat (meniru 'antaraja 2' asli): nama produk tidak termakan
    lanjutan kode ('Plus'+'Burg' -> 'PlusBurg') dan warna tidak tertelan ke kolom
    Kode ('MEDSPO'+'Hitam' -> 'MEDSPOHitam') — semua terbaca utuh dengan
    x_tolerance=1."""
    with pdfplumber.open(io.BytesIO(build_shopee_tight_pdf())) as pdf:
        doc = parse_pdf(pdf)
    assert doc.platform == 'shopee'
    assert doc.warnings == []
    assert [ln.product_name for ln in doc.lines] == [
        'HAUWA Hijab - Medina Sporty S Bergo Instan Melayu Plus Soft Inner',
        'HAUWA Hijab - Medina Instan L Bergo Melayu Plus Soft Inner',
        'HAUWA Hijab - Medina Instan L Bergo Melayu Plus Soft Inner',
    ]
    assert [(ln.sku, ln.variant) for ln in doc.lines] == [
        ('MEDSPO', 'Hitam'),
        ('MEDINA.Burg', 'Burgundy'),
        ('MEDINA.a', 'Tanah'),
    ]
    assert [ln.order_no for ln in doc.lines] == [
        '260831SH2WMTXE', '260831SH7MB0CU', '260831SH7MB0CU',
    ]


def test_tight_pdf_is_a_regression_for_default_tolerance():
    """Akar masalah: ekstraksi default menggabungkan kata antar kolom yang nyaris
    menempel. Fixture sengaja dibuat dengan gap 1.7pt agar bug itu benar muncul di
    default, dan x_tolerance=1 memisahkannya."""
    with pdfplumber.open(io.BytesIO(build_shopee_tight_pdf())) as pdf:
        page = pdf.pages[0]
        merged = ' '.join(w['text'] for w in page.extract_words())
        split = set(w['text'] for w in page.extract_words(x_tolerance=1))
    assert 'MEDSPOHitam' in merged and 'PlusBurg' in merged
    assert not ({'MEDSPOHitam', 'PlusBurg'} & split)
    assert {'MEDSPO', 'Hitam', 'Plus', 'Burg'} <= split


def test_undecodable_glyph_is_normalized_to_dash():
    """Glyph yang gagal didekode pdfplumber (U+FFFD) atau terbaca sebagai en dash
    putus (U+2013, kasus 'antaraja 2' produk Iris) dinormalisasi jadi '-'."""
    from app.parsers.text import join_words, norm
    assert norm('HAUWA Hijab \ufffd Iris Segitiga') == 'HAUWA Hijab - Iris Segitiga'
    assert norm('HAUWA Hijab \u2013 Iris Segitiga') == 'HAUWA Hijab - Iris Segitiga'
    words = [
        {'top': 10, 'x0': 5, 'text': 'HAUWA'},
        {'top': 10, 'x0': 40, 'text': 'Hijab \u2013 Iris'},
    ]
    assert join_words(words, ' ') == 'HAUWA Hijab - Iris'
