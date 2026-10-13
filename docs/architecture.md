# Arsitektur

## Alur data

```
PDF (Shopee/TikTok)
   │  POST /api/parse
   ▼
parsers.parse_pdf ──► ParsedDocument (baris + nomor pesanan + peringatan)
   │
   ▼
services.matching ──► cocokkan ke produk Odoo (kaskade: default_code dulu, baru
                      nama template + warna varian) lewat OdooGateway
   │
   ▼
Frontend: pratinjau & koreksi (customer, produk, qty, harga)
   │
   └─ POST /api/csv ──► services.orders.build_quotations_csv ──► CSV template Quotations
```

## Lapisan backend

| Lapisan | Folder | Tanggung jawab |
|---|---|---|
| HTTP | `app/api/` | Validasi input, kode status, memanggil service |
| Logika | `app/services/` | Pencocokan produk, pengelompokan order, pembuatan CSV (fungsi murni) |
| Integrasi | `app/integrations/odoo/` | `OdooGateway` (Protocol), klien JSON-2, mock |
| Parser | `app/parsers/` | PDF → `ParsedDocument`; tidak bergantung pada Odoo/HTTP |

`get_odoo()` (di `api/deps.py`) memilih klien asli atau mock dari konfigurasi. Tes menimpanya dengan
`MockOdooClient` lewat `app.dependency_overrides`.

## Endpoint

| Method | Path | Fungsi |
|---|---|---|
| GET | `/api/health` | Status koneksi Odoo (`mode`: `odoo` / `mock`) |
| POST | `/api/parse` | Upload PDF → baris + produk cocok + peringatan (field `platform` opsional) |
| GET | `/api/products?q=` | Cari produk (nama / kode) |
| GET | `/api/customers?q=` | Cari customer |
| POST | `/api/csv` | Unduh CSV sesuai template Quotations (nama file `PLATFORM-DDMMYYYY-NAMAPDF-SESI.csv`; sesi 1/2/3 wajib dipilih di UI) |

Kode status: 400 (bukan PDF / rusak / nilai `platform` tidak valid), 413 (terlalu besar), 422
(dokumen tak dikenali, data belum lengkap), 502 (Odoo menolak atau tidak terjangkau).

### Pilihan platform di `/api/parse`

Field form `platform` (`shopee` / `tiktok`) bersifat opsional. Isi PDF tetap menentukan parser:

- deteksi cocok tapi `platform` beda → **ditolak 422**
  `PDF ini terdeteksi sebagai ... tetapi platform yang dipilih ...` (admin pilih ulang);
- deteksi gagal tapi `platform` terisi → pakai pilihan pengguna + warning
  `Platform tidak terdeteksi otomatis; memakai pilihan ...`;
- deteksi gagal tanpa `platform` → 422 seperti biasa;
- nilai di luar `shopee`/`tiktok` → 400.

Frontend mengirim pilihan ini (wajib dipilih admin sebelum upload); error/warning dari backend
tampil sebagai Banner (error mengembalikan ke dropzone).

### Kinerja `/api/parse` (mode Odoo)

Tiap RPC Odoo bisa detik, jadi panggilan independen jalan paralel (`ThreadPoolExecutor`):
`find_products_by_codes` + `find_variants_by_template_names` di `services/matching.py`,
`match_lines` + `search_customers` di `api/parsing.py`. Kata kunci fallback fuzzy diambil
dalam **satu** `find_variants_by_keywords` untuk semua nama lalu dipartisi lokal (jangan
kembalikan ke 1 RPC per nama). `OdooClient` memakai satu `httpx.Client` (keep-alive, lazy
agar tes tetap cepat) + cache 30 detik untuk pencarian combobox. Teks PDF di-extract sekali
di `parse_pdf` lalu diteruskan ke parser platform (jangan extract ulang). Jangan ubah pola
ini tanpa mengukur ulang (`/api/parse` mode Odoo ±5,5 dtk untuk sample 1 halaman).

## Frontend

`features/converter/useConverter.js` memegang seluruh state dan aksi. Komponen di
`features/converter/` dan `components/` hanya menampilkan dan meneruskan event. Semua panggilan
HTTP ada di `api/client.js`; di mode dev, Vite meneruskan `/api` ke `localhost:8000`.
