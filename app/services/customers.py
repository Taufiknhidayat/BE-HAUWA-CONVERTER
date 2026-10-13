"""Logika murni memilih customer marketplace untuk platform tertentu."""
from collections.abc import Iterable

from ..schemas import Customer

# Nama yang diharapkan ada di Odoo per platform (dicocokkan secara longgar).
MARKETPLACE_CUSTOMER = {'shopee': 'Marketplace - Shopee', 'tiktok': 'Marketplace - Tiktok'}

_MARKERS = {'shopee': 'shopee', 'tiktok': 'tiktok'}


def _key(name: str) -> str:
    """Normalisasi untuk perbandingan longgar antar platform: casefold + abjad/angka saja."""
    return ''.join(ch for ch in name.casefold() if ch.isalnum())


def find_marketplace_customer(
    platform: str, customers: Iterable[Customer]
) -> Customer | None:
    """Pilih customer marketplace untuk platform ('shopee'/'tiktok').

    Cocok pada nama yang diawali "marketplace" dan memuat penanda platform, jadi
    tolerant terhadap beda spasi/tanda hubung/kapital (mis. "Marketplace - Shopee",
    "Marketplace-Shopee"). Bila cocok ke lebih dari satu (ambiguous), jangan
    menebak: kembalikan None agar pengguna memilih manual.
    """
    marker = _MARKERS.get(platform)
    if not marker:
        return None
    matched = []
    for c in customers:
        key = _key(c.name)
        if key.startswith('marketplace') and marker in key:
            matched.append(c)
    return matched[0] if len(matched) == 1 else None