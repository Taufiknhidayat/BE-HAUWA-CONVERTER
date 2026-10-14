"""Parser TikTok Shop: dokumen 'Picking List'.

Kolom: No | Product image | Product name | SKU (nama variasi) | Seller SKU | Qty | Order ID

Sifat dokumen:
- Nama produk hanya tertulis sekali per produk; variasinya berupa baris-baris di bawahnya.
- Order ID (angka 18 digit) sejajar dengan baris variasinya. Variasi dengan qty n punya n
  Order ID (baris tambahan di bawahnya). Satu Order ID bisa muncul di banyak baris karena
  satu pesanan berisi beberapa barang.
- Header memuat total ("Order quantity", "Item quantity") yang dipakai untuk memeriksa
  kelengkapan hasil baca.
- Tidak ada harga. Tanggal hanya "Print time" tanpa tahun (MM-DD_hh-mm-ss).
- Logo TikTok tidak muncul sebagai teks, jadi platform dikenali dari judul dan kolomnya.
"""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from .generic import parse_generic
from .text import join_words
from .types import ParsedDocument, ParsedLine

_ORDER_ID = re.compile(r'\d{15,20}')
_PRINT_TIME = re.compile(r'Print time:\s*(\d{2})-(\d{2})')
_ORDER_QTY = re.compile(r'Order quantity:\s*(\d+)', re.IGNORECASE)
_ITEM_QTY = re.compile(r'Item quantity:\s*(\d+)', re.IGNORECASE)


@dataclass
class _Row:
    sku: str | None
    variant: str
    qty: int
    orders: list[str]


@dataclass
class _Product:
    name: str
    rows: list[_Row] = field(default_factory=list)


def _header(words):
    qty = next((w for w in words if w['text'] == 'Qty'), None)
    if not qty:
        return None
    # Header bisa tersebar di 2-3 baris teks: pada PDF asli 'Product' kolom foto
    # berada ~5,8pt di atas baris Qty dan 'image' ~5,8pt di bawahnya, sedangkan
    # baris statistik dokumen ('Order/Product/Item quantity') ~41pt di atas.
    # Band 12pt menampung ketiga baris header tanpa menarik statistik/data.
    same = sorted((w for w in words if abs(w['top'] - qty['top']) < 12), key=lambda w: w['x0'])

    def find(key):
        """Cari kata header: persis dulu, lalu mengandung (varian rapat seperti
        'SellerSKU'/'OrderID' yang kehilangan spasinya)."""
        hit = next((w for w in same if w['text'] == key), None)
        if hit is not None:
            return hit
        return next((w for w in same if key in w['text']), None)

    no = next((w for w in same if w['text'] == 'No'), None)
    order = find('Order')
    seller = find('Seller')
    products = [w for w in same if 'Product' in w['text']]
    skus = [w for w in same
            if 'SKU' in w['text'] and 'Seller' not in w['text']
            and seller and w['x0'] < seller['x0']]
    if not (no and order and seller and len(products) >= 2 and skus):
        return None

    cols = [('no', no['x0']), ('img', products[0]['x0']), ('prod', products[1]['x0']),
            ('var', skus[0]['x0']), ('seller', seller['x0']), ('qty', qty['x0']),
            ('order', order['x0'])]
    cols.sort(key=lambda c: c[1])

    below = [w for w in words if w['text'] == 'image' and qty['top'] < w['top'] < qty['top'] + 40]
    return cols, max([qty['bottom']] + [w['bottom'] for w in below])


def _collect_products(pdf) -> list[_Product]:
    products: list[_Product] = []
    current: _Product | None = None
    cols = None
    for page in pdf.pages:
        # Kolom bisa sangat rapat (gap antar kolom < default 3pt) sehingga kata
        # dari kolom berbeda terkumpul jadi satu token; x_tolerance kecil menjaga
        # kata utuh (gap antar huruf 0, gap antar kata asli > 1).
        words = page.extract_words(x_tolerance=1)
        hdr = _header(words)
        if hdr:
            cols, header_bottom = hdr
        elif cols:
            header_bottom = 0
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
                current = _Product(join_words([w for w in seg if col_of(w) == 'prod'], ' '))
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
                orders = [w['text'] for w in sorted((w for w in row if col_of(w) == 'order'),
                                                    key=lambda w: w['top'])
                          if _ORDER_ID.fullmatch(w['text'])]
                current.rows.append(_Row(
                    sku=join_words([w for w in row if col_of(w) == 'seller'], '') or None,
                    variant=join_words([w for w in row if col_of(w) == 'var'], ' '),
                    qty=int(qa['text']) or 1,
                    orders=orders,
                ))
    return products


def _to_lines(product: _Product, warnings: list[str]) -> list[ParsedLine]:
    """Satu baris variasi -> baris hasil.

    - Jumlah Order ID == qty: satu baris per Order ID, tiap pesanan 1 pcs.
    - Tepat satu Order ID: satu baris dengan qty penuh (satu pesanan berisi n pcs).
    - Selain itu: peringatan, jangan menebak.
    """
    lines: list[ParsedLine] = []
    for r in product.rows:
        name = f'{product.name} - {r.variant}' if r.variant else product.name
        n = len(r.orders)
        if n == r.qty:
            lines += [ParsedLine(name, r.sku, 1.0, order_no=o, product_name=product.name or None,
                                  variant=r.variant or None) for o in r.orders]
        elif n == 1:
            lines.append(ParsedLine(name, r.sku, float(r.qty), order_no=r.orders[0],
                                    product_name=product.name or None, variant=r.variant or None))
        elif n == 0:
            warnings.append(f'"{name}": Order ID tidak terbaca.')
            lines.append(ParsedLine(name, r.sku, float(r.qty), product_name=product.name or None,
                                    variant=r.variant or None))
        else:
            warnings.append(f'"{name}": qty {r.qty} tetapi {n} Order ID terbaca. Periksa baris ini.')
            lines += [ParsedLine(name, r.sku, 1.0, order_no=o, product_name=product.name or None,
                                  variant=r.variant or None) for o in r.orders]
    return lines


def _print_date(text: str) -> str | None:
    """'Print time: 09-01_...' -> tanggal terdekat di masa lalu (dokumen tanpa tahun)."""
    m = _PRINT_TIME.search(text)
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    today = date.today()
    try:
        d = date(today.year, month, day)
        if d > today + timedelta(days=1):
            d = date(today.year - 1, month, day)
    except ValueError:
        return None
    return d.isoformat()


def parse_tiktok(pdf, text: str | None = None) -> ParsedDocument:
    # `text` diisi pemanggil (parse_pdf) supaya extract_text berat tidak diulang.
    if text is None:
        text = '\n'.join((p.extract_text() or '') for p in pdf.pages)
    warnings: list[str] = []
    lines = [ln for p in _collect_products(pdf) for ln in _to_lines(p, warnings)]
    if not lines:
        doc = parse_generic(pdf, platform='tiktok', text=text)
        doc.warnings.append('Format TikTok tidak dikenali penuh, periksa hasilnya dengan teliti.')
        return doc

    # Cocokkan dengan total yang tertulis di header dokumen.
    item_total = _ITEM_QTY.search(text)
    got_qty = int(sum(ln.qty for ln in lines))
    if item_total and int(item_total.group(1)) != got_qty:
        warnings.append(
            f'Total qty terbaca {got_qty}, sedangkan dokumen menulis {item_total.group(1)}. '
            'Mungkin ada baris yang tidak terbaca.')
    order_total = _ORDER_QTY.search(text)
    got_orders = len({ln.order_no for ln in lines if ln.order_no})
    if order_total and int(order_total.group(1)) != got_orders:
        warnings.append(
            f'Jumlah pesanan terbaca {got_orders}, sedangkan dokumen menulis '
            f'{order_total.group(1)}. Mungkin ada baris yang tidak terbaca.')

    first = next((ln.order_no for ln in lines if ln.order_no), None)
    return ParsedDocument('tiktok', first, _print_date(text), lines, warnings)
