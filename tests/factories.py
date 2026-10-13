"""Pembuat PDF tiruan 'Daftar Pesanan Per Produk' Shopee untuk pengujian.

Tata letak meniru dokumen asli: nama produk hanya di baris pertama, kode variasi
terpotong ke beberapa baris, dan nomor pesanan berupa daftar terpisah per produk.
"""
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

_H = A4[1]


def build_shopee_pdf(
    products: list[dict],
    download: str = '02:39 PM 25/08/2026',
    title: str = 'Daftar Pesanan Per Produk',
) -> bytes:
    """products: [{'sku': [...], 'name': [...], 'step': 37,
                   'variants': [{'kode': [...], 'var': str, 'qty': str}],
                   'orders': [str]}]

    `title` bisa diganti untuk membuat PDF yang tidak dikenali deteksi otomatis.
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    def text(x, y, s, size=9, bold=False):
        c.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
        c.drawString(x, _H - y, s)

    text(180, 40, title, 18, True)
    text(20, 70, 'Username: hauwa_official')
    text(20, 85, f'Waktu & Tanggal Download: {download}')
    hy = 120
    for x, s in [(20, '#'), (45, 'SKU'), (100, 'Foto Produk'), (170, 'Nama Produk'), (300, 'Kode'),
                 (350, 'Nama Variasi'), (440, 'Qty'), (470, 'Lokasi'), (510, 'No Pesanan')]:
        text(x, hy, s, 9, True)
    text(45, hy + 11, 'Induk', 9, True)
    text(300, hy + 11, 'Variasi', 9, True)
    c.line(15, _H - hy - 16, 580, _H - hy - 16)

    top = 152
    for n, p in enumerate(products, 1):
        step = p['step']
        text(20, top, str(n))
        for i, s in enumerate(p['sku']):
            text(45, top + 11 * i, s)
        for i, s in enumerate(p['name']):
            text(170, top + 11 * i, s)
        for i, v in enumerate(p['variants']):
            y = top + i * step
            for k, s in enumerate(v['kode']):
                text(300, y + 11 * k, s)
            text(350, y, v['var'])
            text(440, y, v['qty'])
        for i, o in enumerate(p['orders']):
            y = top + i * step
            # Nomor pesanan panjang bisa terpotong dua baris di PDF asli; dukung
            # entri sebagai daftar fragmen (mis. ['260831AAR6J34GNE', 'TFQ']).
            for k, frag in enumerate(o if isinstance(o, list) else [o]):
                text(510, y + 9 * k, frag)
            text(510, y + 14, 'package 1')
        rows = max(len(p['variants']), len(p['orders']))
        top += rows * step + 8
        c.line(15, _H - top + 4, 580, _H - top + 4)
    c.save()
    return buf.getvalue()


# Meniru contoh PDF asli (01/09/2026) termasuk dua ketidaksejajaran nomor pesanan.
SAMPLE_PRODUCTS = [
    {   # 2 variasi, 2 nomor pesanan -> satu variasi satu pesanan
        'sku': ['Medina', 'Series'], 'step': 35,
        'name': ['HAUWA Hijab - Medina 2.0', 'Bergo Tanpa Tali jersey Korea'],
        'variants': [
            {'kode': ['MED 2.0-', '6'], 'var': 'Maroon,L', 'qty': '1'},
            {'kode': ['MED 2.0-', 'm'], 'var': 'Navy,L', 'qty': '1'},
        ],
        'orders': ['260831RRGRKTCM', '260831S9BTQAYN'],
    },
    {   # 2 variasi (qty 2+1) dan 3 nomor pesanan -> qty n memakai n nomor
        'sku': ['Pashmi', 'na Anak'], 'step': 37,
        'name': ['HAUWA Kids - Lolly instan', 'Pashmina Oval Anak'],
        'variants': [
            {'kode': ['pas-', 'Anak-', 'RAYON-2'], 'var': 'Broken White', 'qty': '2'},
            {'kode': ['pas-', 'Anak-', 'RAYON-8'], 'var': 'Khaki', 'qty': '1'},
        ],
        'orders': ['260831S2NPGMX8', '260831SAPSUXHD', '260831SEDYNN73'],
    },
    {   # 3 variasi (total qty 4) tetapi hanya 2 nomor -> tidak konsisten, harus ada peringatan
        'sku': ['Bergo', 'Melayu', 'Instan'], 'step': 26,
        'name': ['HAUWA Hijab - Raya', 'Bergo Melayu Bandana Sport S'],
        'variants': [
            {'kode': ['Raya--S-', '-7'], 'var': 'Khaki', 'qty': '1'},
            {'kode': ['Raya--S-', '-1'], 'var': 'Black', 'qty': '2'},
            {'kode': ['Raya--S-', '-4'], 'var': 'Mahogany', 'qty': '1'},
        ],
        'orders': ['260831S2TWFMEP', '260831S8PTCWK0'],
    },
]


def build_tiktok_pdf(
    products: list[dict],
    stats: str = 'Order quantity: 8   Product quantity: 3   Item quantity: 12',
    print_time: str = '09-01_05-59-29',
) -> bytes:
    """Meniru 'Picking List' TikTok.

    products: [{'name': [...], 'rows': [{'var': str, 'seller': str, 'qty': str, 'orders': [str]}]}]
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(720, 842))

    def text(x, y, s, size=9, bold=False):
        c.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
        c.drawString(x, 842 - y, s)

    text(20, 40, 'Picking List', 22, True)
    text(20, 62, 'User: m***2@gmail.com')
    text(20, 78, f'Print time: {print_time}')
    text(20, 94, stats)
    hy = 130
    for x, s in [(20, 'No'), (55, 'Product'), (130, 'Product'), (180, 'name'), (280, 'SKU'),
                 (360, 'Seller'), (395, 'SKU'), (440, 'Qty'), (480, 'Order'), (510, 'ID')]:
        text(x, hy, s, 9, True)
    text(55, hy + 11, 'image', 9, True)
    c.line(15, 842 - hy - 18, 700, 842 - hy - 18)

    top = 170
    for n, p in enumerate(products, 1):
        text(20, top, str(n))
        for i, s in enumerate(p['name']):
            text(130, top + 12 * i, s)
        y = top
        for r in p['rows']:
            text(280, y, r['var'])
            text(360, y, r['seller'])
            text(440, y, r['qty'])
            for k, o in enumerate(r['orders']):
                text(480, y + 17 * k, o)
            y += max(len(r['orders']), 1) * 17 + 4
        top = max(y, top + 12 * len(p['name'])) + 14
    c.save()
    return buf.getvalue()


TIKTOK_PRODUCTS = [
    {'name': ['HAUWA Safa Pashban - Pashmina', 'Bandana Instan Malay'],
     'rows': [{'var': 'Hitam, L', 'seller': 'Pashban-L-03', 'qty': '1',
               'orders': ['585818319425209790']}]},
    {'name': ['HAUWAM - Medina Sport Series', 'Rayon'],
     'rows': [
         {'var': 'Black', 'seller': 'MEDRAY-1', 'qty': '1', 'orders': ['585820817587340349']},
         {'var': 'Broken White', 'seller': 'MEDRAY-3', 'qty': '1', 'orders': ['585820118813410345']},
         {'var': 'Cool Grey', 'seller': 'MEDRAY-2', 'qty': '1', 'orders': ['585818062502725365']},
         {'var': 'Mocca', 'seller': 'MEDRAY-5', 'qty': '1', 'orders': ['585820817587340349']},
         {'var': 'Taupe', 'seller': 'MEDRAY-4', 'qty': '2',
          'orders': ['585817856053642710', '585820817587340349']},
         {'var': 'Vanilla', 'seller': 'MEDRAY-7', 'qty': '1', 'orders': ['585820817587340349']},
     ]},
    {'name': ['HAUWAM Medina L Instan - Bergo', 'melayu Plus soft Inner'],
     'rows': [
         {'var': 'Abu.Grey', 'seller': 'MEDINA.h', 'qty': '1', 'orders': ['585821035831133337']},
         {'var': 'Cream', 'seller': 'MEDINA.c', 'qty': '1', 'orders': ['585820880466838815']},
         {'var': 'Hazelnut', 'seller': 'MEDINA.l', 'qty': '1', 'orders': ['585821035831133337']},
         {'var': 'Hitam', 'seller': 'MEDINA.gzz', 'qty': '1', 'orders': ['585817882038011554']},
     ]},
]


def build_shopee_tight_pdf() -> bytes:
    """PDF dengan kolom yang nyaris menempel, meniru 'antaraja 2' asli.

    Dengan x_tolerance default pdfplumber (~3pt), dua kata beda kolom yang
    berjarak 1.7pt tergabung jadi satu kata: 'MEDSPO'+'Hitam' -> 'MEDSPOHitam'
    (warna tertelan Kode) dan 'Plus'+'Burg' -> 'PlusBurg' (lanjutan SKU nempel
    ke Nama Produk). Parser memakai x_tolerance=1, jadi semua kata tetap utuh.
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    def text(x, y, s, size=9, bold=False):
        c.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
        c.drawString(x, _H - y, s)

    def width(s):
        return stringWidth(s, 'Helvetica', 9)

    text(180, 40, 'Daftar Pesanan Per Produk', 18, True)
    text(20, 70, 'Username: hauwa_official')
    text(20, 85, 'Waktu & Tanggal Download: 05:54 AM 01/09/2026')
    hy = 120
    for x, s in [(9.2, '#'), (30.2, 'SKU'), (65.4, 'Foto'), (87.3, 'Produk'),
                 (135.0, 'Nama'), (161.9, 'Produk'), (246.5, 'Kode'), (273.0, 'Nama'),
                 (315.4, 'Variasi'), (399.9, 'Qty'), (427.6, 'Lokasi'),
                 (496.5, 'No'), (511.0, 'Pesanan')]:
        text(x, hy, s, 9, True)
    text(30.2, hy + 11, 'Induk', 9, True)
    text(246.5, hy + 11, 'Variasi', 9, True)
    c.line(15, _H - hy - 16, 580, _H - hy - 16)

    # Produk 1 (mirip 'Sporty S' antaraja): warna 'Hitam' nyaris menempel ke
    # kode 'MEDSPO' (gap 1.7) -> 'MEDSPOHitam' bila default x_tolerance.
    y0 = 152
    text(9.2, y0, '1')
    text(135, y0, 'HAUWA Hijab - Medina')
    text(135, y0 + 9, 'Sporty S Bergo Instan')
    text(135, y0 + 18, 'Melayu Plus Soft Inner')
    text(246.5, y0, 'MEDSPO')
    text(246.5 + width('MEDSPO') + 1.7, y0, 'Hitam')
    text(399.9, y0, '1')
    text(496.5, y0, '260831SH2WMTXE')

    # Produk 2 (mirip 'Instan L'): baris kedua nama berakhir 'Plus' tepat di
    # depan lanjutan kode 'Burg' (gap 1.7) -> 'PlusBurg' bila default.
    y1 = y0 + 46
    text(9.2, y1, '2')
    text(135, y1, 'HAUWA Hijab - Medina')
    text(135, y1 + 9, 'Instan L Bergo Melayu Plus')
    text(135, y1 + 18, 'Soft Inner')
    text(246.5, y1, 'MEDINA.')
    text(246.5 + width('MEDINA.') + 4.5, y1, 'Burgundy')
    text(399.9, y1, '1')
    text(496.5, y1, '260831SH7MB0CU')
    text(246.5, y1 + 9, 'Burg')
    y2 = y1 + 38
    text(246.5, y2, 'MEDINA.')
    text(246.5, y2 + 9, 'a')
    text(246.5 + width('MEDINA.') + 1.7, y2, 'Tanah')
    text(399.9, y2, '1')
    text(496.5, y2, '260831SH7MB0CU')

    c.save()
    return buf.getvalue()
