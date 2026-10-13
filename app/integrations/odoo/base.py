from collections.abc import Iterable
from typing import Protocol

from ...schemas import Customer, Health, ProductRef


class OdooError(Exception):
    """Kegagalan saat berkomunikasi dengan Odoo."""


class OdooGateway(Protocol):
    """Kontrak yang dipenuhi klien Odoo asli maupun mock."""

    def health(self) -> Health: ...

    def find_products_by_codes(
        self, codes: Iterable[str]
    ) -> dict[str, list[ProductRef]]: ...

    def find_variants_by_template_names(
        self, names: Iterable[str]
    ) -> dict[str, list[ProductRef]]:
        """Cari varian berdasarkan nama template (mis. nama produk tanpa warna).

        -> nama template (dipetakan apa adanya) -> daftar varian. Tiap varian
        membawa warna (atribut Color/Warna).
        """
        ...

    def find_variants_by_keywords(
        self, terms: Iterable[str]
    ) -> list[ProductRef]:
        """Cari varian lewat kata kunci bebas (nama template memuat salah satu term).

        Dipakai turunan kemiripan nama di `services.matching.py` saat nama produk
        PDF tidak cocok persis dengan nama template Odoo.
        """
        ...

    def search_products(self, q: str, limit: int = 20) -> list[ProductRef]: ...

    def search_customers(self, q: str, limit: int = 20) -> list[Customer]: ...
