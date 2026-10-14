from app.api.deps import get_odoo
from app.integrations.odoo import MockOdooClient
from app.schemas import ProductRef


def _upload(client, content, name='daftar.pdf', platform=None):
    files = {'file': (name, content, 'application/pdf')}
    if platform is None:
        return client.post('/api/parse', files=files)
    return client.post('/api/parse', data={'platform': platform}, files=files)


def test_health_in_mock_mode(client):
    assert client.get('/api/health').json()['mode'] == 'mock'


def test_parse_returns_matched_lines_and_warnings(client, sample_pdf_bytes):
    r = _upload(client, sample_pdf_bytes)
    assert r.status_code == 200
    data = r.json()
    assert data['platform'] == 'shopee'
    assert len(data['lines']) == 7  # 2+2+3 variasi; produk tidak dipecah per nomor pesanan
    # mode demo meniru struktur Odoo: nama template + warna -> semua baris cocok otomatis
    assert all(ln['product'] for ln in data['lines'])
    assert all(ln['product']['color'] for ln in data['lines'])
    # semua produk punya nomor pesanan -> tanpa peringatan parser
    assert data['warnings'] == []
    # customer marketplace otomatis mengikuti platform hasil deteksi
    assert data['customer'] == {'id': 1, 'name': 'Marketplace - Shopee'}


def test_parse_warns_and_leaves_customer_empty_when_marketplace_missing(client, sample_pdf_bytes):
    class NoMarketplaceGateway(MockOdooClient):
        def search_customers(self, q, limit=20):
            return []  # customer "Marketplace - ..." belum dibuat di Odoo

    client.app.dependency_overrides[get_odoo] = NoMarketplaceGateway
    r = _upload(client, sample_pdf_bytes)
    assert r.status_code == 200
    data = r.json()
    assert data['customer'] is None
    assert any('Marketplace - Shopee' in w and 'pilih manual' in w for w in data['warnings'])


def test_parse_rejects_non_pdf(client):
    r = client.post('/api/parse', files={'file': ('x.txt', b'hi', 'text/plain')})
    assert r.status_code == 400


def test_parse_rejects_unknown_document(client):
    r = _upload(client, b'%PDF-1.4 bukan pdf valid')
    assert r.status_code == 400


def test_parse_accepts_matching_platform_hint(client, sample_pdf_bytes):
    r = _upload(client, sample_pdf_bytes, platform='shopee')
    assert r.status_code == 200
    assert r.json()['platform'] == 'shopee'


def test_parse_platform_mismatch_is_rejected(client, sample_pdf_bytes):
    r = _upload(client, sample_pdf_bytes, platform='tiktok')
    assert r.status_code == 422
    assert 'Shopee' in r.json()['detail'] and 'TikTok' in r.json()['detail']


def test_parse_rejects_invalid_platform_value(client, sample_pdf_bytes):
    r = _upload(client, sample_pdf_bytes, platform='shoppe')
    assert r.status_code == 400
    assert 'shopee' in r.json()['detail']


def test_parse_warns_when_sku_matches_multiple_products(client, sample_pdf_bytes):
    class DuplicateGateway(MockOdooClient):
        def find_products_by_codes(self, codes):
            wanted = sorted({c for c in codes if c})
            return {c: [ProductRef(id=1, name='Varian Merah', code=c, price=1000),
                        ProductRef(id=2, name='Varian Biru', code=c, price=1000)]
                    for c in wanted}

        def find_variants_by_template_names(self, names):
            return {}  # nama+warna tidak bisa menyelamatkan di skenario ini

        def find_variants_by_keywords(self, terms):
            return {}  # fallback kemiripan nama juga tidak menemukan apa-apa

    client.app.dependency_overrides[get_odoo] = DuplicateGateway
    r = _upload(client, sample_pdf_bytes)
    assert r.status_code == 200
    data = r.json()
    assert any('2 produk Odoo' in w for w in data['warnings'])
    # SKU ganda tidak boleh dipilih diam-diam: semua baris tetap belum cocok
    assert all(ln['product'] is None for ln in data['lines'])


def test_csv_requires_customer(client, sample_pdf_bytes):
    data = _upload(client, sample_pdf_bytes).json()
    payload = {'customer_name': None, 'lines': data['lines']}
    assert client.post('/api/csv', json=payload).status_code == 422


def test_csv_happy_path_and_filename(client):
    product = {'id': 4, 'name': 'Lalisa Hitam', 'code': 'LALISA.g', 'price': 79000}
    lines = [
        {'name': 'x', 'qty': 1, 'price': 79000, 'order_no': 'A1', 'product': product},
        {'name': 'x', 'qty': 2, 'price': 79000, 'order_no': 'A2', 'product': product},
    ]
    payload = {'customer_name': 'Shopee', 'order_date': '2026-08-25',
               'platform': 'shopee', 'file_name': 'antaraja 2.pdf', 'session': '1', 'lines': lines}
    csv = client.post('/api/csv', json=payload)
    assert csv.status_code == 200
    assert csv.headers['content-type'].startswith('text/csv')
    assert csv.text.splitlines()[0].startswith('Customer*,Order Date')
    assert csv.headers['content-disposition'] == 'attachment; filename="SHOPEE-25082026-ANTARAJA-2-1.csv"'


def test_csv_rejects_missing_session(client):
    product = {'id': 4, 'name': 'Lalisa Hitam', 'code': 'LALISA.g', 'price': 79000}
    lines = [{'name': 'x', 'qty': 1, 'price': 79000, 'order_no': 'A1', 'product': product}]
    payload = {'customer_name': 'Shopee', 'order_date': '2026-08-25',
               'platform': 'shopee', 'file_name': 'antaraja 2.pdf', 'lines': lines}
    r = client.post('/api/csv', json=payload)
    assert r.status_code == 422
    assert 'sesi' in r.json()['detail']
