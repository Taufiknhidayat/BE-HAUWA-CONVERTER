"""Parser generik berbasis header tabel. Dipakai sebagai fallback dan untuk TikTok."""
import re

from .text import to_number
from .types import ParsedDocument, ParsedLine

HEADER_KEYWORDS = {
    'name': ('nama produk', 'product name', 'produk', 'product', 'deskripsi', 'description'),
    'sku': ('sku', 'kode', 'seller sku'),
    'qty': ('qty', 'jumlah', 'quantity', 'kuantitas'),
    'price': ('harga satuan', 'harga', 'unit price', 'price'),
}
REF_PATTERN = re.compile(
    r'(?:no\.?\s*pesanan|order\s*(?:id|no\.?|number)|nomor\s*pesanan)\s*[:#]?\s*([A-Za-z0-9\-]+)',
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(r'(\d{2})[-/](\d{2})[-/](\d{4})')


def _map_header(row):
    mapping = {}
    for idx, cell in enumerate(row):
        c = (cell or '').strip().lower()
        for key, words in HEADER_KEYWORDS.items():
            if key not in mapping and any(w in c for w in words):
                mapping[key] = idx
    return mapping if 'name' in mapping and 'qty' in mapping else None


def parse_generic(pdf, platform: str = 'generic', text: str | None = None) -> ParsedDocument:
    # `text` diisi pemanggil bila sudah di-extract (hemat satu pass penuh).
    if text is None:
        text = '\n'.join((p.extract_text() or '') for p in pdf.pages)
    ref_match = REF_PATTERN.search(text)
    date_match = DATE_PATTERN.search(text)
    date = None
    if date_match:
        d, m, y = date_match.groups()
        date = f'{y}-{m}-{d}'

    lines: list[ParsedLine] = []
    for page in pdf.pages:
        for table in page.extract_tables():
            mapping = None
            for row in table:
                if mapping is None:
                    mapping = _map_header(row)
                    continue
                name = (row[mapping['name']] or '').replace('\n', ' ').strip()
                if not name:
                    continue
                lines.append(ParsedLine(
                    name=name,
                    sku=(row[mapping['sku']] or '').strip() if 'sku' in mapping else None,
                    qty=to_number(row[mapping['qty']]) or 1.0,
                    price=to_number(row[mapping['price']]) if 'price' in mapping else 0.0,
                ))
    return ParsedDocument(platform, ref_match.group(1) if ref_match else None, date, lines)
