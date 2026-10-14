"""Pengganti Odoo untuk mode demo dan pengujian. Tidak menghubungi jaringan.

Katalog demo meniru struktur produk Odoo saat ini: nama template tanpa warna,
warna disimpan sebagai atribut varian (Color/Warna), Internal Reference kosong.
"""
from collections.abc import Iterable

from ...schemas import Customer, Health, ProductRef

_TEMPLATES: dict[str, list[dict]] = {
    'HAUWA Hijab - Medina 2.0 Bergo Tanpa Tali jersey Korea': [
        {'color': 'Maroon', 'price': 89000, 'taxes': ['PPN 11%'], 'tax_ids': [5]},
        {'color': 'Navy', 'price': 89000, 'taxes': ['PPN 11%'], 'tax_ids': [5]},
    ],
    'HAUWA Kids - Lolly instan Pashmina Oval Anak': [
        {'color': 'Broken White', 'price': 65000},
        {'color': 'Khaki', 'price': 65000},
    ],
    'HAUWA Hijab - Raya Bergo Melayu Bandana Sport S': [
        {'color': 'Khaki', 'price': 75000},
        {'color': 'Black', 'price': 75000},
        {'color': 'Mahogany', 'price': 75000},
    ],
}


def _build_catalog() -> list[ProductRef]:
    products: list[ProductRef] = []
    ident = 0
    for name, variants in _TEMPLATES.items():
        for v in variants:
            ident += 1
            products.append(ProductRef(
                id=ident, name=name, code=None, price=v['price'],
                color=v['color'], taxes=v.get('taxes', []), tax_ids=v.get('tax_ids', []),
            ))
    return products


_PRODUCTS = _build_catalog()
_CUSTOMERS = [
    Customer(id=1, name='Marketplace - Shopee'),
    Customer(id=2, name='Marketplace - Tiktok'),
    Customer(id=3, name='Hauwa Official'),
]


class MockOdooClient:
    def health(self) -> Health:
        return Health(mode='mock', connected=True, detail='Mode demo (data contoh)')

    def find_products_by_codes(
        self, codes: Iterable[str]
    ) -> dict[str, list[ProductRef]]:
        wanted = {c for c in codes if c}
        return {p.code: [p] for p in _PRODUCTS if p.code in wanted}

    def find_variants_by_template_names(
        self, names: Iterable[str]
    ) -> dict[str, list[ProductRef]]:
        wanted = {n for n in names if n}
        return {
            n: [p for p in _PRODUCTS if n.casefold() in p.name.casefold()]
            for n in wanted
        } if wanted else {}

    def find_variants_by_keywords(self, terms: Iterable[str]) -> list[ProductRef]:
        wanted = {t.casefold() for t in terms if t}
        if not wanted:
            return []
        return [p for p in _PRODUCTS if any(t in p.name.casefold() for t in wanted)]

    def search_products(self, q: str, limit: int = 20) -> list[ProductRef]:
        ql = q.lower()
        return [p for p in _PRODUCTS if ql in p.name.lower() or ql in (p.code or '').lower()][:limit]

    def search_customers(self, q: str, limit: int = 20) -> list[Customer]:
        return [c for c in _CUSTOMERS if q.lower() in c.name.lower()][:limit]