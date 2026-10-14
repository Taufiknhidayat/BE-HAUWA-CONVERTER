from app.config import Settings
from app.integrations.odoo.client import OdooClient


def _client(monkeypatch, recs):
    client = OdooClient(Settings('http://odoo.example', 'db', 'key', False))
    monkeypatch.setattr(client, '_call', lambda *a, **k: recs)
    return client


def _client_seq(monkeypatch, responses):
    """_call mengembalikan respons berurutan (untuk metode 2-3 panggilan)."""
    client = OdooClient(Settings('http://odoo.example', 'db', 'key', False))
    calls = list(responses)

    def fake_call(model, method, payload):
        return calls.pop(0)

    monkeypatch.setattr(client, '_call', fake_call)
    return client


def test_find_products_by_codes_groups_products_sharing_a_code(monkeypatch):
    recs = [
        {'id': 1, 'name': 'Varian Merah', 'default_code': 'SKU-A', 'list_price': 1000},
        {'id': 2, 'name': 'Varian Biru', 'default_code': 'SKU-A', 'list_price': 1000},
        {'id': 3, 'name': 'Satu', 'default_code': 'SKU-B', 'list_price': 500},
    ]
    grouped = _client(monkeypatch, recs).find_products_by_codes(
        ['SKU-A', 'SKU-B', 'SKU-A'])
    assert sorted(grouped) == ['SKU-A', 'SKU-B']
    assert [p.name for p in grouped['SKU-A']] == ['Varian Merah', 'Varian Biru']
    assert [p.name for p in grouped['SKU-B']] == ['Satu']


def test_find_products_by_codes_skips_missing_code(monkeypatch):
    recs = [{'id': 9, 'name': 'Tanpa Kode', 'default_code': None, 'list_price': 1}]
    assert _client(monkeypatch, recs).find_products_by_codes(['X']) == {}


def test_find_products_by_codes_empty_input(monkeypatch):
    assert _client(monkeypatch, []).find_products_by_codes([]) == {}


def test_find_variants_by_template_names_groups_by_template_and_parses_color(monkeypatch):
    templates = [{'id': 10, 'name': 'Kain Raya Bermotif L'}]
    products = [
        {'id': 1, 'name': 'Kain Raya Bermotif L', 'default_code': None,
         'list_price': 75000, 'import_attribute_values': 'Warna:Maroon',
         'product_tmpl_id': [10, 'Kain Raya Bermotif L']},
        {'id': 2, 'name': 'Kain Raya Bermotif L', 'default_code': 'RAYA.H',
         'list_price': 79000, 'import_attribute_values': 'Color:Hitam,Size:L',
         'product_tmpl_id': [10, 'Kain Raya Bermotif L']},
    ]
    client = _client_seq(monkeypatch, [templates, products])
    grouped = client.find_variants_by_template_names(['Kain Raya Bermotif L'])
    variants = grouped['Kain Raya Bermotif L']
    assert [p.name for p in variants] == ['Kain Raya Bermotif L', 'Kain Raya Bermotif L']
    maroon, hitam = variants
    assert maroon.color == 'Maroon' and maroon.code is None
    assert hitam.color == 'Hitam' and hitam.code == 'RAYA.H'


def test_find_variants_by_template_names_empty_input(monkeypatch):
    client = _client_seq(monkeypatch, [])
    assert client.find_variants_by_template_names([]) == {}


def test_search_products_includes_color(monkeypatch):
    products = [
        {'id': 1, 'name': 'Kain Raya', 'default_code': None, 'list_price': 75000,
         'import_attribute_values': 'Color:Maroon', 'product_tmpl_id': [10, 'Kain Raya']},
    ]
    client = _client_seq(monkeypatch, [products])
    out = client.search_products('kain')
    assert out[0].color == 'Maroon'


def test_product_taxes_resolved_to_names_in_single_call(monkeypatch):
    """taxes_id produk di-resolve ke nama pajak lewat satu search_read account.tax."""
    products = [
        {'id': 1, 'name': 'A', 'default_code': 'A', 'list_price': 1000, 'taxes_id': [5, 7]},
        {'id': 2, 'name': 'B', 'default_code': 'B', 'list_price': 2000, 'taxes_id': [5]},
    ]
    taxes = [{'id': 5, 'name': 'PPN 11%'}, {'id': 7, 'name': 'PPh 22'}]
    client = _client_seq(monkeypatch, [products, taxes])
    grouped = client.find_products_by_codes(['A', 'B'])
    assert grouped['A'][0].taxes == ['PPN 11%', 'PPh 22']
    assert grouped['A'][0].tax_ids == [5, 7]
    assert grouped['B'][0].taxes == ['PPN 11%']
    assert grouped['B'][0].tax_ids == [5]


def test_product_without_taxes_makes_no_extra_call(monkeypatch):
    """Produk tanpa pajak tidak memicu RPC account.tax (respons habis = gagal
    bila ada panggilan lebih, karena _client_seq pop dari list kosong)."""
    products = [
        {'id': 1, 'name': 'A', 'default_code': 'A', 'list_price': 1000, 'taxes_id': []},
    ]
    client = _client_seq(monkeypatch, [products])
    assert client.find_products_by_codes(['A'])['A'][0].taxes == []
