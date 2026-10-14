"""Klien Odoo 19 lewat External JSON-2 API: POST /json/2/<model>/<method>."""
import time
from collections.abc import Iterable

import httpx

from ...config import Settings
from ...schemas import Customer, Health, ProductRef
from .base import OdooError

_PRODUCT_FIELDS = ['id', 'name', 'default_code', 'list_price', 'import_attribute_values',
                   'taxes_id']
_COLOR_ATTR_NAMES = ('color', 'warna')


def _product(rec: dict) -> ProductRef:
    return ProductRef(
        id=rec['id'], name=rec['name'],
        code=rec.get('default_code') or None,
        price=float(rec.get('list_price') or 0),
        color=_color_from_import(rec.get('import_attribute_values')),
    )


def _tax_ids(rec: dict) -> list[int]:
    """Id pajak dari `taxes_id` produk (many2many Odoo berupa list id)."""
    return [i for i in (rec.get('taxes_id') or []) if isinstance(i, int)]


def _color_from_import(values) -> str | None:
    """Ambil nilai atribut warna dari kolom `import_attribute_values` Odoo.

    Formatnya "Color:Maroon" atau "Color:Maroon,Size:L". Nama atribut bisa
    "Color" atau "Warna" (terjemahan). Kalau atributnya cuma satu dan namanya
    bukan Color/Warna, nilainya tetap dipakai.
    """
    if not values:
        return None
    attrs = []
    for part in values.split(','):
        name, sep, val = part.partition(':')
        if sep and name.strip() and val.strip():
            attrs.append((name.strip().casefold(), val.strip()))
    if not attrs:
        return None
    for key, val in attrs:
        if key in _COLOR_ATTR_NAMES:
            return val
    return attrs[0][1] if len(attrs) == 1 else None


class OdooClient:
    # Hasil pencarian combobox di-cache sebentar: mengetik "medina" memicu
    # banyak request beruntun dengan query berulang; master produk tidak
    # berubah dalam hitungan detik sehingga cache 30 detik aman. Ukuran
    # dibatasi agar entri kedaluwarsa tidak menumpuk di server lama hidup.
    _SEARCH_TTL = 30.0
    _SEARCH_MAX = 200

    def __init__(self, settings: Settings):
        self._url = settings.odoo_url
        self._db = settings.odoo_db
        self._key = settings.odoo_api_key
        # Koneksi dibuat malas (lazy): membangun httpx.Client butuh ~0,5 dtk
        # (konteks SSL), jadi hanya saat panggilan nyata pertama. Aman dipakai
        # bergantian antar thread; balapan saat init hanya membuang satu klien.
        self._http: httpx.Client | None = None
        self._search_cache: dict[tuple, tuple[float, object]] = {}

    def _cached_search(self, key: tuple, loader):
        now = time.monotonic()
        hit = self._search_cache.get(key)
        if hit is not None and now - hit[0] < self._SEARCH_TTL:
            return hit[1]
        value = loader()
        if len(self._search_cache) >= self._SEARCH_MAX:
            self._search_cache.pop(next(iter(self._search_cache)))
        self._search_cache[key] = (now, value)
        return value

    def _call(self, model: str, method: str, payload: dict):
        if self._http is None:
            # Satu koneksi dipakai ulang (keep-alive) agar tiap RPC tidak
            # handshake/TLS baru.
            self._http = httpx.Client(timeout=30)
        headers = {'Authorization': f'bearer {self._key}'}
        if self._db:
            headers['X-Odoo-Database'] = self._db
        try:
            r = self._http.post(f'{self._url}/json/2/{model}/{method}',
                                json=payload, headers=headers)
        except httpx.HTTPError as e:
            raise OdooError(f'Tidak bisa terhubung ke Odoo: {e}') from e
        if r.status_code >= 400:
            try:
                body = r.json()
                msg = body.get('message') or body.get('name') or r.text
            except ValueError:
                msg = r.text
            raise OdooError(f'Odoo menolak permintaan ({r.status_code}): {msg}')
        return r.json()

    def _with_taxes(self, recs: list[dict]) -> list[ProductRef]:
        """Bangun ProductRef dari record produk + nama pajaknya.

        Id pajak (`taxes_id`) di-resolve ke nama lewat SATU `search_read`
        `account.tax` untuk seluruh id unik (bukan satu RPC per produk); nama
        di-cache karena master pajak jarang berubah. Tanpa id pajak -> tanpa
        RPC tambahan, `taxes` tetap kosong.
        """
        products = [_product(r) for r in recs]
        wanted = sorted({i for r in recs for i in _tax_ids(r)})
        if not wanted:
            return products

        def load():
            rows = self._call('account.tax', 'search_read', {
                'domain': [['id', 'in', wanted]], 'fields': ['id', 'name']})
            return {r['id']: r['name'] for r in rows}

        names = self._cached_search(('taxes', tuple(wanted)), load)
        for p, r in zip(products, recs, strict=True):
            ids = _tax_ids(r)
            p.tax_ids = ids
            p.taxes = [names[i] for i in ids if i in names]
        return products

    def health(self) -> Health:
        try:
            self._call('res.partner', 'search_read',
                       {'domain': [], 'fields': ['id'], 'limit': 1})
            return Health(mode='odoo', connected=True, detail=self._url)
        except OdooError as e:
            return Health(mode='odoo', connected=False, detail=str(e))

    def find_products_by_codes(
        self, codes: Iterable[str]
    ) -> dict[str, list[ProductRef]]:
        codes = sorted({c for c in codes if c})
        if not codes:
            return {}
        recs = self._call('product.product', 'search_read', {
            'domain': [['default_code', 'in', codes]], 'fields': _PRODUCT_FIELDS})
        grouped: dict[str, list[ProductRef]] = {}
        for r, p in zip(recs, self._with_taxes(recs), strict=True):
            code = r.get('default_code')
            if code:
                grouped.setdefault(code, []).append(p)
        return grouped

    def find_variants_by_template_names(
        self, names: Iterable[str]
    ) -> dict[str, list[ProductRef]]:
        names = [n for n in dict.fromkeys(names) if n]
        if not names:
            return {}
        doms = [[('name', 'ilike', n)] for n in names]
        domain = doms[0] if len(doms) == 1 \
            else ['|'] * (len(doms) - 1) + [d for pair in doms for d in pair]
        templates = self._call('product.template', 'search_read', {
            'domain': domain, 'fields': ['id', 'name']})
        tmpl_ids = [t['id'] for t in templates]
        recs = self._call('product.product', 'search_read', {
            'domain': [['product_tmpl_id', 'in', tmpl_ids]],
            'fields': ['product_tmpl_id', *_PRODUCT_FIELDS]})
        name_by_id = {t['id']: t['name'] for t in templates}
        grouped: dict[str, list[ProductRef]] = {}
        for r, p in zip(recs, self._with_taxes(recs), strict=True):
            tmpl_id = r.get('product_tmpl_id')
            name = name_by_id.get(tmpl_id[0], r['name']) if tmpl_id else r['name']
            grouped.setdefault(name, []).append(p)
        return grouped

    def find_variants_by_keywords(self, terms) -> list[ProductRef]:
        """Cari varian lewat kata kunci: template yang namanya memuat salah satu
        term. (fallback kemiripan nama di matching, lihat services/matching.py)."""
        terms = [t for t in dict.fromkeys(terms) if t]
        if not terms:
            return []
        doms = [[('name', 'ilike', t)] for t in terms]
        domain = doms[0] if len(doms) == 1 \
            else ['|'] * (len(doms) - 1) + [d for pair in doms for d in pair]
        templates = self._call('product.template', 'search_read', {
            'domain': domain, 'fields': ['id', 'name'], 'limit': 200})
        tmpl_ids = [t['id'] for t in templates]
        if not tmpl_ids:
            return []
        recs = self._call('product.product', 'search_read', {
            'domain': [['product_tmpl_id', 'in', tmpl_ids]],
            'fields': ['product_tmpl_id', *_PRODUCT_FIELDS]})
        return self._with_taxes(recs)

    def search_products(self, q: str, limit: int = 20) -> list[ProductRef]:
        def load():
            domain = ['|', ['name', 'ilike', q], ['default_code', 'ilike', q]] if q else []
            recs = self._call('product.product', 'search_read', {
                'domain': domain,
                'fields': ['product_tmpl_id', *_PRODUCT_FIELDS],
                'limit': limit})
            return self._with_taxes(recs)
        return self._cached_search(('products', q, limit), load)

    def search_customers(self, q: str, limit: int = 20) -> list[Customer]:
        def load():
            recs = self._call('res.partner', 'search_read', {
                'domain': [['name', 'ilike', q]] if q else [],
                'fields': ['id', 'name'], 'limit': limit})
            return [Customer(id=r['id'], name=r['name']) for r in recs]
        return self._cached_search(('customers', q, limit), load)
