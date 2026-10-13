"""Parser Shopee: dokumen 'Daftar Pesanan Per Produk'.

Kolom: # | SKU Induk | Foto Produk | Nama Produk | Kode Variasi | Nama Variasi |
       Qty | Lokasi | No Pesanan

Sifat dokumen yang harus diperhatikan:
- Satu produk punya beberapa baris variasi; Nama Produk (dan SKU Induk) hanya tertulis
  sekali per produk (sel digabung).
- Kolom No Pesanan adalah daftar nomor pesanan milik produk itu ("<nomor> package 1").
  Posisi vertikalnya tidak selalu sejajar dengan baris variasi, dan jumlahnya bisa
  berbeda dari jumlah variasi (satu warna dengan total qty besar bisa muncul di
  banyak pesanan). Qty per nomor tidak bisa dipastikan, jadi tiap produk menjadi
  satu Sales Order dan nomor pertama dipakai sebagai Customer Reference.
- Nomor pesanan panjang sering terpotong ke baris kedua; parser menyusunnya lagi.
- Kode Variasi sering terpotong ke baris kedua ("LALISA.B" + "urg").
- Tidak ada harga. Tanggal pesanan = waktu download di baris atas
  ("Waktu & Tanggal Download: 09:23 AM 01/09/2026", format DD/MM/YYYY).

Parser membaca posisi kata (x/y), bukan sel tabel. Baris variasi dikenali dari angka di
kolom Qty. Nomor pesanan dikumpulkan per produk dan disusun ulang lewat
`_merge_order_tokens`; satu produk menjadi satu Sales Order (`_variants_to_lines`).
Parser berbasis tabel dipertahankan sebagai fallback.
"""
import re
from dataclasses import dataclass, field

from .generic import parse_generic
from .text import join_words, norm, to_number
from .types import ParsedDocument, ParsedLine

# Tanggal baca DD/MM/YYYY lalu diubah ke ISO. Regex toleran: titik dua boleh
# diberi spasi / diganti tanda lain, dan jarak maksimum ke tanggal dibatasi
# (agar tidak menangkap tanggal lain di satu baris teks).
_DOWNLOAD_DATE = re.compile(
    r'Download\s*[:.\-]?\s*.{0,40}?(\d{1,2})/(\d{1,2})/(\d{2,4})',
    re.IGNORECASE | re.DOTALL)
# Nomor pesanan panjang sering terpotong dua baris di PDF, mis.
# "260831AAR6J34GNE" + "TFQ". Fragmen utuh (>= 10 karakter) memulai nomor baru;
# fragmen pendek berhuruf kapital/angka adalah lanjutannya. Kata seperti
# "package 1" (huruf kecil) diabaikan karena tidak cocok pola ini.
_ORDER_TOKEN = re.compile(r'[A-Z0-9]+')
_ORDER_MIN_LEN = 10


@dataclass
class _Variant:
    sku: str | None
    name: str
    qty: int


@dataclass
class _Product:
    name: str
    variants: list[_Variant] = field(default_factory=list)
    orders: list[str] = field(default_factory=list)


def _header(words):
    """Cari posisi kolom dari baris header. -> (kolom, batas_bawah_header) | None"""
    qty = next((w for w in words if w['text'] == 'Qty'), None)
    if not qty:
        return None
    same = sorted((w for w in words if abs(w['top'] - qty['top']) < 3), key=lambda w: w['x0'])

    def pick(t):
        return next((w for w in same if w['text'] == t), None)

    hash_w, sku, foto, kode, lok, no = (
        pick('#'), pick('SKU'), pick('Foto'), pick('Kode'), pick('Lokasi'), pick('No'))
    namas = [w for w in same if w['text'] == 'Nama']
    if not (hash_w and kode and no and len(namas) >= 2):
        return None

    cols = [('no', hash_w['x0'])]
    if sku:
        cols.append(('sku', sku['x0']))
    if foto:
        cols.append(('foto', foto['x0']))
    cols += [('prod', namas[0]['x0']), ('kode', kode['x0']), ('var', namas[1]['x0']),
             ('qty', qty['x0'])]
    if lok:
        cols.append(('lok', lok['x0']))
    cols.append(('order', no['x0']))
    cols.sort(key=lambda c: c[1])

    line_h = qty['bottom'] - qty['top']
    second_line = [
        w for w in words
        if qty['top'] + 3 < w['top'] < qty['top'] + 4 * line_h
        and ((w['text'] == 'Induk' and sku and abs(w['x0'] - sku['x0']) < 5)
             or (w['text'] == 'Variasi' and abs(w['x0'] - kode['x0']) < 5))
    ]
    return cols, max([qty['bottom']] + [w['bottom'] for w in second_line])


def _merge_order_tokens(tokens) -> list[str]:
    """Susun ulang nomor pesanan yang terpotong beberapa baris di PDF.

    Token panjang (>= `_ORDER_MIN_LEN`) memulai nomor baru; token pendek yang
    mengandung huruf kapital (mis. "TFQ") ditempelkan ke nomor sebelumnya.
    Token lain (mis. "package" dan angka "1") dilewati.
    """
    orders: list[str] = []
    for text in tokens:
        if not _ORDER_TOKEN.fullmatch(text) or not re.search(r'[A-Z]', text):
            continue
        if len(text) >= _ORDER_MIN_LEN:
            orders.append(text)
        elif orders:
            orders[-1] += text
    return orders


def _collect_products(pdf) -> list[_Product]:
    products: list[_Product] = []
    current: _Product | None = None
    cols = None
    for page in pdf.pages:
        # x_tolerance kecil: kolom PDF ini sangat rapat dan teks antar kolom bisa
        # nyaris menempel (gap ~1.7pt, di bawah default 3pt) sehingga pdfplumber
        # mengaburkan dua kolom jadi satu kata — mis. nama "Plus" + lanjutan SKU
        # "Burg" jadi "PlusBurg" dan warna "Hitam" tertelan ke Kode. Gap antar
        # kata asli ~2.5pt dan antar huruf 0, jadi kata tetap utuh dengan 1.
        words = page.extract_words(x_tolerance=1)
        hdr = _header(words)
        if hdr:
            cols, header_bottom = hdr
        elif cols:
            header_bottom = 0  # halaman lanjutan tanpa header
        else:
            continue

        def col_of(w, cols=cols):
            name = None
            for cname, x in cols:
                if w['x0'] + 4 >= x:
                    name = cname
            return name

        data = [w for w in words if w['top'] >= header_bottom]
        anchors = sorted(
            (w for w in data if col_of(w) == 'no' and re.fullmatch(r'\d+', w['text'])),
            key=lambda w: w['top'])

        # Segmen vertikal: (anchor produk | None bila lanjutan dari halaman sebelumnya, y0, y1)
        segments = []
        first_top = anchors[0]['top'] - 2 if anchors else page.height
        if current is not None and first_top > header_bottom:
            segments.append((None, header_bottom, first_top))
        for i, a in enumerate(anchors):
            y1 = anchors[i + 1]['top'] - 2 if i + 1 < len(anchors) else page.height
            segments.append((a, a['top'] - 2, y1))

        for anchor, y0, y1 in segments:
            seg = [w for w in data if y0 <= w['top'] < y1]
            if anchor is not None:
                name = join_words([w for w in seg if col_of(w) == 'prod'], ' ')
                current = _Product(name)
                products.append(current)
            if current is None:
                continue

            qty_anchors = sorted(
                (w for w in seg if col_of(w) == 'qty' and re.fullmatch(r'\d+', w['text'])),
                key=lambda w: w['top'])
            for j, qa in enumerate(qty_anchors):
                r0 = qa['top'] - 2
                r1 = qty_anchors[j + 1]['top'] - 2 if j + 1 < len(qty_anchors) else y1
                row = [w for w in seg if r0 <= w['top'] < r1]
                current.variants.append(_Variant(
                    sku=join_words([w for w in row if col_of(w) == 'kode'], '') or None,
                    name=join_words([w for w in row if col_of(w) == 'var'], ' '),
                    qty=int(qa['text']) or 1,
                ))
            current.orders += _merge_order_tokens(
                w['text'] for w in sorted((w for w in seg if col_of(w) == 'order'),
                                          key=lambda w: w['top']))
    return products


def _variants_to_lines(product: _Product, warnings: list[str]) -> list[ParsedLine]:
    """Ubah satu produk menjadi baris-baris hasil, tanpa menebak pasangan order.

    Dokumen 'Daftar Pesanan Per Produk' mengelompokkan per produk: kolom Qty dan
    Nama Variasi memuat total per warna, sedangkan No Pesanan bisa berisi banyak
    nomor (satu pembeli satu nomor, banyak pembeli banyak nomor). Qty per nomor
    tidak bisa dipastikan dari dokumen, jadi tiap produk menjadi **satu Sales
    Order** (lihat `services/orders.group_orders`) dengan order line per warna,
    dan nomor pesanan pertama dipakai sebagai Customer Reference. Tidak ada
    nomor yang dibuang dan tidak ada tebakan pasangan nomor-variasi.
    """
    if not product.orders:
        warnings.append(f'"{product.name}": nomor pesanan tidak terbaca.')
    first = product.orders[0] if product.orders else None
    return [
        ParsedLine(
            name=f'{product.name} - {v.name}' if v.name else product.name,
            sku=v.sku,
            qty=float(v.qty),
            order_no=first,
            product_name=product.name or None,
            variant=v.name or None,
        )
        for v in product.variants
    ]


def _parse_table(pdf) -> list[ParsedLine]:
    """Fallback bila posisi kata tidak bisa dipakai (mis. layout berbeda)."""
    lines: list[ParsedLine] = []
    for page in pdf.pages:
        for table in page.extract_tables():
            idx = None
            for row in table:
                cells = [norm(c).lower() for c in row]
                if idx is None:
                    if 'nama produk' in cells and 'qty' in cells:
                        idx = {c: i for i, c in enumerate(cells)}
                    continue
                name = norm(row[idx['nama produk']])
                if not name:
                    continue
                variant = norm(row[idx['nama variasi']]) if 'nama variasi' in idx else ''
                sku = norm(row[idx['kode variasi']]) if 'kode variasi' in idx else ''
                order_no = ''
                if 'no pesanan' in idx:
                    merged = _merge_order_tokens(norm(row[idx['no pesanan']]).split(' '))
                    order_no = merged[0] if merged else ''
                lines.append(ParsedLine(
                    name=f'{name} - {variant}' if variant else name,
                    sku=sku or None,
                    qty=to_number(row[idx['qty']]) or 1.0,
                    order_no=order_no or None,
                    product_name=name or None,
                    variant=variant or None,
                ))
    return lines


def parse_shopee(pdf, text: str | None = None) -> ParsedDocument:
    # `text` diisi pemanggil (parse_pdf) supaya extract_text berat tidak diulang.
    if text is None:
        text = '\n'.join((p.extract_text() or '') for p in pdf.pages)
    date = None
    m = _DOWNLOAD_DATE.search(text)
    if m:
        # DD/MM/YYYY (konfirmasi pengguna: "01/09/2026" = 1 September); tahun 2 digit dilengkapi.
        d, mo, y = m.groups()
        if len(y) == 2:
            y = f'20{y}'
        date = f'{y}-{mo}-{d}'  # tanggal download dipakai sebagai tanggal order default

    warnings: list[str] = []
    lines = [ln for p in _collect_products(pdf) for ln in _variants_to_lines(p, warnings)]
    if not lines:
        lines = _parse_table(pdf)
    if not lines:
        return parse_generic(pdf, platform='shopee', text=text)
    refs = [ln.order_no for ln in lines if ln.order_no]
    return ParsedDocument('shopee', refs[0] if refs else None, date, lines, warnings)
