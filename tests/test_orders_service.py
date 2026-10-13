import pytest

from app.schemas import Line, ProductRef, SubmitIn
from app.services.orders import (
    CSV_HEADER,
    OrderValidationError,
    _date_iso,
    build_quotations_csv,
    csv_filename,
    group_orders,
)


def _line(order_no, name='Produk', qty=1.0, code='X'):
    return Line(name=name, qty=qty, price=1000, order_no=order_no,
                product=ProductRef(id=1, name=name, code=code, price=1000))


def _body(**kw):
    base = dict(customer_name='Shopee', order_date='2026-08-25',
                lines=[_line('A1'), _line('A2'), _line('A1', 'Lain')])
    return SubmitIn(**{**base, **kw})


def test_split_groups_lines_by_order_number():
    groups = group_orders(_body())
    assert [(ref, len(lines)) for ref, lines in groups] == [('A1', 2), ('A2', 1)]


def test_no_split_makes_single_order():
    groups = group_orders(_body(split=False, order_ref='REF'))
    assert [(ref, len(lines)) for ref, lines in groups] == [('REF', 3)]


def test_shopee_split_groups_by_product_not_order_number():
    body = SubmitIn(
        customer_name='Marketplace - Shopee', order_date='2026-08-25',
        platform='shopee',
        lines=[
            Line(name='Bergo - Hitam', qty=2, order_no='ORD1', product_name='Bergo',
                 product=ProductRef(id=1, name='Bergo', code='B1', price=100)),
            Line(name='Bergo - Putih', qty=1, order_no='ORD1', product_name='Bergo',
                 product=ProductRef(id=2, name='Bergo', code='B2', price=100)),
            Line(name='Sport - Hitam', qty=3, order_no='ORD2', product_name='Sport',
                 product=ProductRef(id=3, name='Sport', code='S1', price=100)),
        ],
    )
    groups = group_orders(body)
    # 2 produk -> 2 Sales Order; Customer Reference = nomor pesanan pertama grup
    assert [(ref, len(ls)) for ref, ls in groups] == [('ORD1', 2), ('ORD2', 1)]


def test_shopee_no_split_merges_all_lines():
    body = SubmitIn(
        customer_name='Marketplace - Shopee', order_date='2026-08-25',
        platform='shopee', split=False, order_ref='REF',
        lines=[
            Line(name='Bergo - Hitam', qty=2, order_no='ORD1', product_name='Bergo',
                 product=ProductRef(id=1, name='Bergo', code='B1', price=100)),
            Line(name='Sport - Hitam', qty=3, order_no='ORD2', product_name='Sport',
                 product=ProductRef(id=3, name='Sport', code='S1', price=100)),
        ],
    )
    groups = group_orders(body)
    assert [(ref, len(ls)) for ref, ls in groups] == [('REF', 2)]


def test_csv_matches_odoo_quotation_template():
    rows = build_quotations_csv(_body()).strip().splitlines()
    assert rows[0].split(',') == CSV_HEADER
    # order A1 (2 baris): header order hanya di baris pertama, tanggal ISO,
    # kolom produk memakai Database ID varian (unik antar-warna), bukan nama
    assert rows[1].startswith('Shopee,2026-08-25,,,1,1,1000')
    assert rows[1].endswith(',,,A1,')
    assert rows[2].startswith(',,,,1,')
    assert rows[3].startswith('Shopee,')


def test_csv_product_column_uses_variant_database_id():
    body = _body(lines=[
        Line(name='Dari PDF', qty=1, price=1, order_no='A1',
             product=ProductRef(id=10, name='Nama Odoo', code=None, price=1)),
        Line(name='Nama dari PDF', qty=1, price=1, order_no='A2',
             product=ProductRef(id=20, name='Varian Lain', code='SKU.2', price=1)),
        Line(name='Belum Cocok', qty=1, price=1, order_no='A3', product=None),
    ])
    cols = [r.split(',')[4] for r in build_quotations_csv(body).strip().splitlines()[1:]]
    # Database ID varian; hanya baris tanpa produk yang jatuh ke nama PDF
    assert cols == ['10', '20', 'Belum Cocok']


def test_csv_writes_whole_numbers_without_decimal():
    body = _body(lines=[
        Line(name='Bulat', qty=2.0, price=79000.0, order_no='A1',
             product=ProductRef(id=1, name='Bulat', code='B', price=79000.0)),
        Line(name='Pecahan', qty=1.5, price=1.98, order_no='A2',
             product=ProductRef(id=2, name='Pecahan', code='P', price=1.98)),
    ])
    rows = build_quotations_csv(body).strip().splitlines()[1:]
    assert rows[0].split(',')[4:7] == ['1', '2', '79000']
    assert rows[1].split(',')[4:7] == ['2', '1.5', '1.98']


def test_csv_date_uses_iso_and_keeps_empty_values():
    assert _date_iso('2026-12-05') == '2026-12-05'
    assert _date_iso('2026-08-25') == '2026-08-25'
    assert _date_iso('2026-08-25 14:41:14') == '2026-08-25'
    assert _date_iso('') == ''
    assert _date_iso(None) == ''
    assert _date_iso('bukan-tanggal') == 'bukan-tanggal'  # jangan dibuang diam-diam
    rows = build_quotations_csv(_body(order_date=None)).strip().splitlines()
    assert rows[1].split(',')[1] == ''


def test_csv_filename_pattern():
    assert csv_filename('shopee', '2026-09-01', 'antaraja 2.pdf', '1') == \
        'SHOPEE-01092026-ANTARAJA-2-1.csv'
    assert csv_filename('tiktok', '2026-09-01', 'tiktok itsnan 1.pdf', '2') == \
        'TIKTOK-01092026-ITSNAN-1-2.csv'


def test_csv_filename_strips_platform_word_and_sanitizes():
    # Kata platform dibuang dari nama PDF agar tidak dobel; karakter aneh dibersihkan.
    assert csv_filename('shopee', '2026-09-01', 'Shopee Itsnan (1).PDF', '3') == \
        'SHOPEE-01092026-ITSNAN-1-3.csv'
    assert csv_filename(None, None, None, '1').startswith('PDF-')
    assert csv_filename(None, None, None, '1').endswith('-PDF-1.csv')


def test_csv_filename_rejects_missing_or_invalid_session():
    with pytest.raises(OrderValidationError, match='sesi'):
        csv_filename('shopee', '2026-09-01', 'antaraja 2.pdf', None)
    with pytest.raises(OrderValidationError, match='sesi'):
        csv_filename('shopee', '2026-09-01', 'antaraja 2.pdf', '4')
