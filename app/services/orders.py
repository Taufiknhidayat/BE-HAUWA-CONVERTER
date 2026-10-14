"""Logika murni untuk mengelompokkan baris menjadi order dan membuat CSV Odoo."""
import csv
import io
import re
from datetime import datetime

from ..schemas import Line, SubmitIn

# Urutan dan nama kolom mengikuti "Import Template for Quotations" Odoo 19,
# tanpa kolom 'Order Reference': kalau header-nya ikut tapi isinya kosong,
# import Odoo menolak ("Missing Required value"). Nomor SO dibuat otomatis.
#
# Kolom produk memakai subfield "Database ID" (bukan nama seperti template
# resmi): nama template sama untuk semua warna, sehingga import Odoo by-name
# menemukan banyak match ("Found multiple matches") dan bisa salah varian.
# Database ID unik per varian, jadi tak ambigu tanpa mengubah data Odoo.
CSV_HEADER = [
    'Customer*', 'Order Date', 'Expiration', 'Payment Terms',
    'Order Lines/Products/Database ID', 'Order Lines/Quantity',
    'Order Lines/Unit Price', 'Order Lines/Taxes/Database ID', 'Sales Team',
    'Customer Reference', 'Tags',
]


class OrderValidationError(Exception):
    pass


def _num(value: float) -> str:
    """Tulis angka seperti template Odoo: '12' dan '1.98', bukan '12.0'."""
    f = float(value)
    return str(int(f)) if f.is_integer() else str(f)


def _date_iso(value: str | None) -> str:
    """Normalisasi tanggal ke `YYYY-MM-DD`.

    Format ISO adalah satu-satunya format teks yang selalu terdeteksi benar
    oleh import Odoo (pola lain ditebak dari bahasa user dan bisa terbalik
    antara hari dan bulan). Nilai kosong tetap kosong; bukan ISO
    dikembalikan apa adanya supaya data tidak diam-diam hilang.
    """
    if not value:
        return ''
    try:
        parsed = datetime.strptime(value[:10], '%Y-%m-%d')
    except ValueError:
        return value
    return parsed.strftime('%Y-%m-%d')


def _first_ref(lines: list[Line], fallback: str | None) -> str | None:
    """Customer Reference grup = nomor pesanan pertama di antara barisnya."""
    return next((ln.order_no for ln in lines if ln.order_no), fallback)


# Kata platform dibuang dari bagian nama PDF agar tidak dobel
# ('tiktok itsnan 1.pdf' -> 'ITSNAN-1', bukan 'TIKTOK-ITSNAN-1').
_PLATFORM_WORDS = {'shopee', 'tiktok'}


# Nilai sesi yang sah (dipilih admin lewat 3 tombol di UI).
SESSIONS = ('1', '2', '3')


def csv_filename(platform: str | None, order_date: str | None,
                 file_name: str | None, session: str | None = None) -> str:
    """Nama file CSV: `PLATFORM-DDMMYYYY-NAMAPDF-SESI.csv` (semua kapital).

    Contoh: ('shopee', '2026-09-01', 'antaraja 2.pdf', '1')
    -> 'SHOPEE-01092026-ANTARAJA-2-1.csv'. Data kosong memakai fallback
    ('PDF' / tanggal hari ini) supaya nama file tidak pernah rusak, kecuali
    sesi: wajib '1'/'2'/'3', selain itu OrderValidationError (422 di API).
    """
    if session not in SESSIONS:
        raise OrderValidationError('Pilih sesi (1/2/3) terlebih dahulu.')
    plat = (platform or '').strip().upper() or 'PDF'
    try:
        stamp = datetime.strptime((order_date or '')[:10], '%Y-%m-%d').strftime('%d%m%Y')
    except ValueError:
        digits = re.sub(r'\D', '', order_date or '')
        stamp = digits if len(digits) == 8 else datetime.now().strftime('%d%m%Y')
    base = (file_name or '').rsplit('.', 1)[0]  # buang ekstensi
    words = [w for w in re.findall(r'[a-z0-9]+', base.casefold())
             if w not in _PLATFORM_WORDS]
    name = '-'.join(words).upper() or 'PDF'
    return f'{plat}-{stamp}-{name}-{session}.csv'


def _group_key(value: str | None, fallback: str) -> str:
    """Kunci grup toleran kapitalisasi/spasi: "AZZELA ..." dan "Azzela ..." adalah
    satu produk yang sama sehingga harus menjadi satu Sales Order."""
    return ' '.join((value or fallback).split()).casefold()


def group_orders(body: SubmitIn) -> list[tuple[str | None, list[Line]]]:
    """-> [(customer_ref, baris), ...].

    split=False: semua baris digabung jadi satu order.
    Shopee: **satu Sales Order per produk**. PDF 'Daftar Pesanan Per Produk'
    menulis banyak No. Pesanan di bawah satu produk dan qty per nomor tidak bisa
    dipastikan, jadi mengelompokkan per nomor akan memproduksi SO ganda/salah.
    Platform lain (mis. TikTok): satu No Pesanan satu order.
    """
    if not body.split:
        return [(body.order_ref, body.lines)]
    if body.platform == 'shopee':
        groups: dict[str, list[Line]] = {}
        for ln in body.lines:
            groups.setdefault(_group_key(ln.product_name, ln.name), []).append(ln)
        return [(_first_ref(lines, body.order_ref), lines) for lines in groups.values()]
    groups: dict[str | None, list[Line]] = {}  # platform lain: per No. Pesanan
    for ln in body.lines:
        groups.setdefault(ln.order_no or body.order_ref, []).append(ln)
    return list(groups.items())


def build_quotations_csv(body: SubmitIn) -> str:
    if not body.customer_name:
        raise OrderValidationError('Customer belum dipilih.')
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_HEADER)
    for ref, lines in group_orders(body):
        for i, ln in enumerate(lines):
            first = i == 0  # kolom header order hanya diisi di baris pertama
            w.writerow([
                body.customer_name if first else '',
                _date_iso(body.order_date) if first else '',
                '', '',
                # Database ID varian: unik per warna, jadi import Odoo tidak
                # ambigu (nama template sama untuk semua varian). Fallback ke
                # nama PDF hanya bila produk belum dipilih (dicegah di UI).
                str(ln.product.id) if ln.product else ln.name,
                _num(ln.qty), _num(ln.price),
                # Pajak dari produk Odoo sebagai Database ID (unik per record),
                # koma-dipisah bila >1; kosong bila produk tidak punya pajak.
                # ID dipakai karena NAMA pajak bisa kembar di Odoo (mis. Sales
                # vs Purchase bernama sama) sehingga import by-name menolak
                # ("Found more than one match") — pola yang sama seperti kolom
                # produk (Products/Database ID).
                ','.join(str(i) for i in ln.product.tax_ids) if ln.product else '',
                '',
                (ref or '') if first else '',  # Customer Reference
                '',
            ])
    return buf.getvalue()
