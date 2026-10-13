# BE-HAUWA-CONVERTER

Backend untuk aplikasi pengubah **PDF daftar pesanan marketplace (Shopee, TikTok)** menjadi
**Sales Order (Quotation) di Odoo 19**. Dibangun dengan Python + FastAPI. Frontend ada di repo
terpisah (`FE-HAUWA-CONVERTER`).

## Menjalankan

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env                               # kosongkan ODOO_API_KEY = mode demo
uvicorn app.main:app --reload --port 8000
```

Tanpa `ODOO_API_KEY`, aplikasi berjalan di **mode demo** (data contoh, tanpa jaringan ke Odoo).
Cara menghubungkan ke Odoo ada di [`docs/odoo-integration.md`](docs/odoo-integration.md).

## Endpoint

| Method | Path | Fungsi |
|---|---|---|
| GET | `/api/health` | Status koneksi Odoo (`mode`: `odoo` / `mock`) |
| POST | `/api/parse` | Upload PDF → baris + produk cocok + peringatan |
| GET | `/api/products?q=` | Cari produk (nama / kode) |
| GET | `/api/customers?q=` | Cari customer |
| POST | `/api/csv` | Unduh CSV sesuai template Quotations Odoo |

Alur dan detail endpoint ada di [`docs/architecture.md`](docs/architecture.md).

## Pengembangan

```bash
pytest
ruff check .
```

Aturan lapisan: `api/` hanya menerjemahkan HTTP; logika bisnis di `services/`; semua komunikasi
ke Odoo lewat `OdooGateway` di `integrations/odoo/`; parser tidak boleh tahu soal Odoo atau HTTP.

## Produksi (satu server)

```bash
# dari repo frontend: npm ci && npm run build, salin hasilnya ke frontend/dist
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Backend otomatis menyajikan `frontend/dist` bila folder itu ada.

## Jangan commit

`.env`, API key, atau PDF asli yang berisi data pelanggan. Untuk tes, buat PDF tiruan lewat
`tests/factories.py`.
