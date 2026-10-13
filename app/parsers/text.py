import re

# pdfplumber gagal decode sebagian glyph tanda baca (mis. tanda strip rusak)
# menjadi U+FFFD, atau membacanya sebagai en/em dash (U+2013/U+2014) yang di
# PDF justru tampil putus. Semua itu dinormalisasi ke '-' agar nama produk
# konsisten dengan tanda hubung biasa di produk lain.
_DASH_RE = re.compile(r'[\u2010\u2011\u2012\u2013\u2014\u2015\ufffd]')


def to_number(value) -> float:
    """'Rp 1.250.000' -> 1250000.0, '1,5' -> 1.5, '2.500,75' -> 2500.75"""
    if value is None:
        return 0.0
    s = re.sub(r'[^\d.,-]', '', str(value))
    if not s:
        return 0.0
    if '.' in s and ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.') if len(s.split(',')[-1]) != 3 else s.replace(',', '')
    elif '.' in s and len(s.split('.')[-1]) == 3:
        s = s.replace('.', '')
    try:
        return float(s)
    except ValueError:
        return 0.0


def _clean_dash(text: str) -> str:
    return _DASH_RE.sub('-', text)


def norm(cell) -> str:
    """Rapikan sel tabel: newline dan spasi ganda jadi satu spasi."""
    return _clean_dash(re.sub(r'\s+', ' ', (cell or '').replace('\n', ' ')).strip())


_LINE_TOLERANCE = 3  # selisih 'top' (pt) yang masih dianggap satu baris teks


def join_words(words, line_sep: str) -> str:
    """Gabung kata hasil extract_words: satu baris dipisah spasi, antar baris `line_sep`.

    Kode SKU memakai line_sep='' karena terpotong otomatis oleh lebar kolom (bukan spasi
    asli), sedangkan spasi di dalam satu baris adalah spasi asli.
    """
    lines: list[list[str]] = []
    line_top = None
    for w in sorted(words, key=lambda w: (w['top'], w['x0'])):
        if line_top is None or abs(w['top'] - line_top) > _LINE_TOLERANCE:
            lines.append([])
            line_top = w['top']
        lines[-1].append(_clean_dash(w['text']))
    return line_sep.join(' '.join(parts) for parts in lines)
