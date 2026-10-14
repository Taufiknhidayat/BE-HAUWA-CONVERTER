"""Tes endpoint batch banyak PDF: digabung, atomik, tanggal disamakan, batas."""
from app.api.deps import get_odoo
from app.integrations.odoo import MockOdooClient

from .factories import SAMPLE_PRODUCTS, build_shopee_pdf


def _upload_batch(client, items, platform=None):
    """items: [(nama_file, bytes), ...] -> respons POST /api/parse-batch."""
    files = [('files', (name, content, 'application/pdf')) for name, content in items]
    if platform is None:
        return client.post('/api/parse-batch', files=files)
    return client.post('/api/parse-batch', data={'platform': platform}, files=files)


class _CountingGateway(MockOdooClient):
    def __init__(self):
        self.template_calls = []

    def find_variants_by_template_names(self, names):
        self.template_calls.append(sorted(names))
        return super().find_variants_by_template_names(names)


def test_batch_merges_two_pdfs_with_shared_lookup(client, sample_pdf_bytes):
    gw = _CountingGateway()
    client.app.dependency_overrides[get_odoo] = lambda: gw
    r = _upload_batch(client, [('senin-1.pdf', sample_pdf_bytes),
                               ('senin-2.pdf', sample_pdf_bytes)])
    assert r.status_code == 200
    data = r.json()
    assert data['platform'] == 'shopee'
    assert len(data['lines']) == 14  # 7 baris per PDF
    assert data['files'] == ['senin-1.pdf', 'senin-2.pdf']
    assert data['file_name'] == 'gabungan-2-file'
    assert [ln['source_file'] for ln in data['lines'][:7]] == ['senin-1.pdf'] * 7
    assert [ln['source_file'] for ln in data['lines'][7:]] == ['senin-2.pdf'] * 7
    # Lookup template ke Odoo hanya sekali untuk seluruh batch (bukan per file).
    assert len(gw.template_calls) == 1
    assert data['warnings'] == []


def test_batch_skips_invalid_file_and_marks_it(client, sample_pdf_bytes):
    r = _upload_batch(client, [('bagus.pdf', sample_pdf_bytes),
                               ('rusak.pdf', b'%PDF-1.4 bukan pdf valid')])
    assert r.status_code == 200
    data = r.json()
    assert len(data['lines']) == 7  # hanya file yang berhasil
    assert data['files'] == ['bagus.pdf']
    assert data['file_name'] == 'gabungan-1-file'
    assert len(data['failed']) == 1
    assert data['failed'][0]['file'] == 'rusak.pdf'
    assert data['failed'][0]['error']
    assert any('dilewati' in w and 'rusak.pdf' in w for w in data['warnings'])


def test_batch_skips_minority_platform(client, sample_pdf_bytes, tiktok_pdf_bytes):
    r = _upload_batch(client, [('s1.pdf', sample_pdf_bytes),
                               ('s2.pdf', sample_pdf_bytes),
                               ('t.pdf', tiktok_pdf_bytes)])
    assert r.status_code == 200
    data = r.json()
    assert data['platform'] == 'shopee'
    assert data['files'] == ['s1.pdf', 's2.pdf']
    assert len(data['failed']) == 1
    assert data['failed'][0]['file'] == 't.pdf'
    assert 'berbeda dari batch' in data['failed'][0]['error']


def test_batch_rejects_when_all_files_fail(client):
    r = _upload_batch(client, [('a.pdf', b'%PDF-1.4 bukan pdf'),
                               ('b.txt', b'hi')])
    assert r.status_code == 422
    detail = r.json()['detail']
    assert 'a.pdf' in detail and 'b.txt' in detail


def test_batch_unifies_order_dates(client):
    sama = build_shopee_pdf(SAMPLE_PRODUCTS, download='02:39 PM 25/08/2026')
    beda = build_shopee_pdf(SAMPLE_PRODUCTS, download='10:00 AM 26/08/2026')
    r = _upload_batch(client, [('sama-1.pdf', sama), ('sama-2.pdf', sama),
                               ('beda.pdf', beda)])
    assert r.status_code == 200
    data = r.json()
    # Tanggal terbanyak yang dipakai; file yang beda disebut di peringatan.
    assert data['order_date'] == '2026-08-25'
    assert any('disamakan' in w and '2026-08-26' in w for w in data['warnings'])


def test_batch_rejects_too_many_files(client, sample_pdf_bytes):
    items = [(f'f{i}.pdf', sample_pdf_bytes) for i in range(51)]
    r = _upload_batch(client, items)
    assert r.status_code == 422
    assert '50' in r.json()['detail']


def test_batch_skips_file_matching_other_platform_choice(
    client, sample_pdf_bytes, tiktok_pdf_bytes,
):
    r = _upload_batch(client, [('s.pdf', sample_pdf_bytes),
                               ('t.pdf', tiktok_pdf_bytes)], platform='shopee')
    assert r.status_code == 200
    data = r.json()
    assert data['platform'] == 'shopee'
    assert data['files'] == ['s.pdf']
    assert data['failed'][0]['file'] == 't.pdf'


def test_batch_skips_non_pdf_and_oversize_files(client, sample_pdf_bytes):
    r = client.post('/api/parse-batch',
                    files=[('files', ('bagus.pdf', sample_pdf_bytes, 'application/pdf')),
                           ('files', ('catatan.txt', b'hi', 'text/plain'))])
    assert r.status_code == 200
    data = r.json()
    assert data['files'] == ['bagus.pdf']
    assert data['failed'][0]['file'] == 'catatan.txt'
