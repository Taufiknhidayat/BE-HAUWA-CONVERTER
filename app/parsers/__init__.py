"""Parser dokumen PDF marketplace. Titik masuk: parse_pdf()."""
import re

from .errors import EmptyDocumentError, ParseError, PlatformMismatchError, UnknownPlatformError
from .shopee import parse_shopee
from .tiktok import parse_tiktok
from .types import ParsedDocument, ParsedLine

PARSERS = {'shopee': parse_shopee, 'tiktok': parse_tiktok}
PLATFORM_LABEL = {'shopee': 'Shopee', 'tiktok': 'TikTok'}

# Varian TikTok yang teksnya rapat bisa kehilangan spasi ("SellerSKU", "OrderID",
# "Productname"); polanya memakai \s* agar tetap dikenali.
_TIKTOK_MARKERS = [re.compile(p) for p in
                   (r'picking\s*list', r'seller\s*sku', r'order\s*id')]


def detect_platform(text: str) -> str | None:
    t = text.lower()
    # Logo Shopee berupa gambar (tidak ada di teks PDF), jadi kenali juga dari judul dokumen.
    if 'shopee' in t or 'daftar pesanan per produk' in t:
        return 'shopee'
    # Logo TikTok juga gambar; dokumen "Picking List" dikenali dari judul dan kolomnya.
    if 'tiktok' in t or all(p.search(t) for p in _TIKTOK_MARKERS):
        return 'tiktok'
    return None


def parse_pdf(pdf, platform: str | None = None) -> ParsedDocument:
    """Baca PDF menjadi ParsedDocument.

    `platform` adalah pilihan wajib pengguna di UI: bila bertentangan dengan hasil
    deteksi isi PDF, dokumen DITOLAK (bukan warning) supaya admin memperbaiki
    pilihannya. Bila deteksi gagal total, pilihan pengguna dipakai sebagai jalan
    terakhir (warning) agar dokumen tetap bisa dibaca.
    """
    text = '\n'.join((p.extract_text() or '') for p in pdf.pages)
    detected = detect_platform(text)
    hint_warnings: list[str] = []
    if detected:
        chosen = detected
        # Nilai di luar PARSERS dianggap tidak ada petunjuk; validasinya ada di lapisan API.
        if platform in PARSERS and platform != detected:
            raise PlatformMismatchError(
                f'PDF ini terdeteksi sebagai {PLATFORM_LABEL[detected]}, tetapi platform '
                f'yang dipilih {PLATFORM_LABEL.get(platform, platform)}. '
                'Pilih platform yang sesuai lalu upload ulang.'
            )
    elif platform in PARSERS:
        # Penanda platform tidak ada di teks (mis. judul berubah), pilihan pengguna dipakai
        # sebagai jalan terakhir supaya dokumen tetap terbaca.
        chosen = platform
        hint_warnings.append(
            f'Platform tidak terdeteksi otomatis; memakai pilihan {PLATFORM_LABEL[chosen]}.'
        )
    else:
        raise UnknownPlatformError('Platform tidak dikenali (bukan dokumen Shopee atau TikTok).')
    doc = PARSERS[chosen](pdf, text)
    if not doc.lines:
        raise EmptyDocumentError('Tidak ada baris produk yang berhasil dibaca dari PDF ini.')
    doc.warnings[:0] = hint_warnings  # peringatan platform dibaca lebih dulu
    return doc


__all__ = [
    'PARSERS', 'PLATFORM_LABEL', 'EmptyDocumentError', 'ParseError', 'ParsedDocument',
    'ParsedLine', 'PlatformMismatchError', 'UnknownPlatformError', 'detect_platform', 'parse_pdf',
]
