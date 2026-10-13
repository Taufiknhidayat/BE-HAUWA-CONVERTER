# AGENTS.md

Panduan untuk AI coding assistant (opencode, Claude Code, Codex, Cursor, dll.) dan kontributor
baru. Baca file ini sebelum mengubah kode.

opencode membaca `AGENTS.md` ini otomatis dari root proyek. Dokumen lanjutan di `docs/`
(`architecture.md`, `odoo-integration.md`) dimuat lewat `opencode.json` (field `instructions`),
karena opencode tidak membaca referensi file yang ditulis di dalam `AGENTS.md`.

## Ringkasan proyek

Web app yang mengubah **PDF daftar pesanan marketplace (Shopee, TikTok)** menjadi **Sales Order
(Quotation) di Odoo 19**. Pengguna upload PDF, produk dicocokkan ke master data Odoo, hasilnya bisa
dikoreksi di tabel, lalu dikirim ke Odoo lewat API atau diunduh sebagai CSV sesuai template import
Odoo. Aplikasi ini dipakai klien, jadi tampilan dan pesan error harus rapi dan berbahasa Indonesia.

Status: backend dan frontend berjalan dan teruji di **mode demo**, dengan parser Shopee dan
TikTok. Belum diuji terhadap instance Odoo 19 asli dan PDF asli (lihat "Batasan yang diketahui").

## Instruksi untuk agent

- Balas dan tulis teks UI, pesan error, serta komentar dalam **Bahasa Indonesia**.
- Jalankan perintah dari folder yang tepat: `backend/` untuk Python, `frontend/` untuk npm.
- Sebelum menyatakan selesai, jalankan `pytest`, `ruff check .` (di `backend/`) dan
  `npm run lint`, `npm run build` (di `frontend/`), lalu laporkan hasilnya apa adanya.
- Kerjakan di mode demo (`ODOO_API_KEY` kosong). Jangan mengarahkan perintah apa pun ke Odoo
  produksi dan jangan membuka atau mencetak isi `.env`.
- Kalau data PDF atau struktur produk Odoo ambigu, tanyakan atau beri peringatan; jangan menebak.
- Ubah seperlunya saja. Perubahan perilaku parser harus disertai tes baru di `backend/tests/`.

## Konteks domain (penting, jangan ditebak ulang)

- Targetnya **Sales** (`sale.order`, Customer), **bukan Purchase**. Template yang benar adalah
  "Import Template for Quotations" (kolom: Order Reference, Customer*, Order Date, Expiration,
  Payment Terms, Order Lines/Products*, Quantity, Unit Price, Taxes, Sales Team, Customer
  Reference, Tags). Template RFQ (Purchase) pernah terkirim karena salah, abaikan. **Penyimpangan
  yang disengaja:** kolom produk memakai header `Order Lines/Products/Database ID` (Database ID
  varian), bukan `Order Lines/Products*` seperti template resmi — lihat alasan di bawah.
- Pengelompokan Sales Order bergantung platform (field `platform` di `SubmitIn`, logika di
  `services/orders.group_orders`): **Shopee = satu produk di PDF satu Sales Order** (PDF jelas
  menulis banyak No. Pesanan per produk tanpa membagi qty per nomor, jadi mengelompokkan per
  nomor memproduksi SO ganda/salah). TikTok = **satu No. Pesanan satu Sales Order**. `split=false`
  selalu menggabung semua baris menjadi satu order. Customer Reference = **nomor pesanan
  pertama** dari grup.
- Customer dipilih satu kali untuk seluruh PDF (PDF tidak memuat nama pembeli). Setelah parse,
  customer **"Marketplace - Shopee"** / **"Marketplace - Tiktok"** dicari otomatis di Odoo
  (`services/customers.py`, pencocokan longgar terhadap hasil `search_customers('Marketplace')`)
  dan diisi di UI; bila tidak ditemukan atau ambigu → peringatan dan pilih manual. User tetap
  bisa mengganti customer lewat combobox.
- Pencocokan produk (Shopee): **kaskade dua langkah** di `services/matching.py` —
  1. Kode Variasi dicocokkan ke **Internal Reference** (`default_code`) `product.product`.
     Kode yang cocok ke **lebih dari satu** produk ditampung (bukan dipilih diam-diam).
  2. Bila kode tidak cocok (atau terisi ganda): cocokkan **nama produk dari PDF → nama
     template Odoo** (normalisasi huruf/spasi) **+ warna** yang diambil dari Nama Variasi
      (token sebelum tanda koma) terhadap atribut varian **"Color"/"Warna"** (nilai dibanding
      case-insensitive **tanpa memedulikan spasi/hubung/underscore**, mis. Shopee `BrokenWhite`
      = Odoo `Broken White`). `find_variants_by_template_names` mengambil daftar
      varian per template dan `import_attribute_values` untuk membaca warnanya.
  - Varian Odoo saat ini **belum punya Internal Reference**, jadi langkah 2 adalah jalur utama.
  - Hasil tidak cocok / warna tak ada / warna cocok ke >1 varian → peringatan dan pilih manual
    di tabel; menebak diam-diam membuat Sales Order yang salah. Pengecualian: template dengan
    **hanya satu varian** tetap dipilih otomatis **hanya bila warna PDF tidak terbaca/kosong** —
    itu satu-satunya pilihan yang pasti, bukan tebakan. Bila warna PDF terbaca tapi tidak cocok
    dengan varian Odoo (mis. PDF `Green`, Odoo cuma punya `Black`) → **jangan auto-pick**;
    kosongkan dulu dan beri peringatan pilih manual. Ambiguitas nyata (>1 kandidat) tetap manual.
  - TikTok: masih lewat `default_code` saja (cara baru menyusul).
- Harga default = **Sales Price** (`list_price`); PDF Shopee dan TikTok tidak memuat harga.
- Tanggal order default = tanggal download di PDF, karena tanggal pesanan tidak tercantum.
- **CSV mengikuti template Odoo** (file rujukan: `docs/quotations_import_template.xlsx`): tanggal
  `YYYY-MM-DD` (via `_date_iso`; format lain bisa terbaca terbalik hari/bulan saat import), qty/harga
  tanpa `.0` (via `_num`), kolom `Order Reference` **tidak dicantumkan** karena
  Odoo menolak header kosong ("Missing Required value"); Odoo membuat nomor SO sendiri.
  Kolom produk memakai header `Order Lines/Products/Database ID` berisi **Database ID varian**
  (`product.id`), bukan nama seperti template resmi: nama template sama untuk semua warna sehingga
  import Odoo by-name menemukan banyak match ("Found multiple matches") dan bisa salah varian.
  Database ID unik per varian, jadi CSV selalu tepat warnanya tanpa mengubah data Odoo.
- **Pilihan platform di UI wajib** (admin memilih Shopee/TikTok sebelum upload) dan dikirim sebagai
  field form `platform` di `POST /api/parse`. Pilihan yang bertentangan dengan hasil deteksi isi
  PDF **ditolak (422)** — admin harus pilih yang sesuai lalu upload ulang. Bila deteksi gagal total,
  pilihan pengguna dipakai sebagai jalan terakhir (warning).
- Odoo 19: pakai **JSON-2 API** (`/json/2/<model>/<method>`, header `Authorization: bearer <key>`).
  XML-RPC/JSON-RPC sudah deprecated, jangan dipakai. Odoo tidak mengimpor PO/SO lewat XML; impor
  bawaan hanya CSV/XLSX.
- `ODOO_URL` wajib pakai **`http://127.0.0.1:8069`**, jangan `http://localhost:8069`: di Windows
  `localhost` di-resolve Python ke `::1` dulu dan koneksinya nyangkut ±2 dtk sebelum fallback ke
  IPv4 (curl tidak kena karena Happy Eyeballs). Pajak 2 dtk ini dibayar **tiap RPC** karena server
  menutup koneksi tiap respons — pernah membuat `/api/parse` 11 dtk.

### Format PDF Shopee "Daftar Pesanan Per Produk"

- Kolom: `# | SKU Induk | Foto Produk | Nama Produk | Kode Variasi | Nama Variasi | Qty | Lokasi | No Pesanan`.
- Baris atas memuat waktu download yang dipakai sebagai tanggal order default:
  `Waktu & Tanggal Download: 09:23 AM 01/09/2026` (format **DD/MM/YYYY**; parser
  `_DOWNLOAD_DATE` toleran spasi di sekitar `:` dan menormalisasi ke ISO).
- Logo Shopee adalah **gambar**, bukan teks. Deteksi platform memakai judul dokumen.
- Nama Produk hanya tertulis di baris pertama tiap produk (sel digabung).
- Kolom bisa sangat rapat: teks antar kolom nyaris menempel (gap ~1.7pt, di bawah
  default pdfplumber 3pt), sehingga kata dari dua kolom bisa tergabung — mis. nama
  "Plus" (akhir baris Nama) + lanjutan SKU "Burg" (awal kolom Kode) jadi "PlusBurg",
  atau warna "Hitam" tertelan ke Kode jadi "MEDSPOHitam". Parser membaca kata dengan
  `extract_words(x_tolerance=1)` (gap antar kata asli ~2.5pt dan antar huruf 0, jadi
  kata tetap utuh). Glyph yang gagal didekode (U+FFFD) dinormalisasi ke `-`.
- Kode Variasi terpotong ke beberapa baris. Spasi dalam satu baris adalah spasi asli
  (`MED 2.0-` + `6` -> `MED 2.0-6`); pemotongan antar baris tidak menambah spasi.
- Kolom No Pesanan adalah daftar per produk, posisi vertikalnya tidak selalu sejajar dengan
  variasi. Nomor panjang sering **terpotong dua baris**; `_merge_order_tokens` di
  `parsers/shopee.py` menyusunnya kembali (fragmen pendek berupa huruf kapital/angka ditempel
  ke nomor sebelumnya). Karena qty per nomor tidak bisa dipastikan, **tiap produk menjadi satu
  Sales Order** lewat `_variants_to_lines`: satu baris per variasi dengan qty agregat dan
  Customer Reference = nomor pesanan pertama (`services/orders.group_orders` memakai
  `product_name`). Jika nomor pesanan tidak terbaca sama sekali → peringatan.

### Format PDF TikTok "Picking List"

- Kolom: `No | Product image | Product name | SKU (nama variasi, mis. "Hitam, L") | Seller SKU | Qty | Order ID`.
- Header dokumen memuat `Order quantity`, `Product quantity`, `Item quantity`. Parser memakainya
  untuk memeriksa kelengkapan: total qty dan jumlah pesanan terbaca harus cocok, kalau tidak
  ada peringatan.
- Order ID (18 digit) sejajar dengan baris variasi. Variasi dengan qty n punya n Order ID; satu
  Order ID bisa muncul di banyak baris (satu pesanan berisi beberapa barang).
- Aturan baris: jumlah Order ID == qty -> satu baris per Order ID (1 pcs); tepat satu Order ID ->
  satu baris dengan qty penuh; selain itu peringatan.
- "Print time" hanya `MM-DD_hh-mm-ss` tanpa tahun; tahun diambil dari hari ini (mundur satu
  tahun bila tanggalnya jatuh di masa depan). Logo TikTok bukan teks; platform dikenali dari
  judul "Picking List" dan kolom `Seller SKU` / `Order ID`.

## Tech stack

- Backend: Python 3.11+, FastAPI, pdfplumber, httpx. Uji: pytest. Lint: ruff.
- Frontend: React 19, JavaScript (JSX), Vite, Tailwind CSS v4, lucide-react.
- Integrasi: Odoo 19 JSON-2 API. Mode demo memakai `MockOdooClient` (tanpa jaringan).

## Struktur direktori

```
backend/
  app/
    main.py                  # create_app(): router, error handler, static frontend
    config.py                # Settings dari env (.env)
    schemas.py               # model request/response (pydantic)
    api/                     # lapisan HTTP tipis: health, parsing, catalog, orders, deps
    services/                # logika murni: matching.py (cocokkan produk), orders.py (grouping, CSV)
    integrations/odoo/       # base.py (Protocol), client.py (JSON-2), mock.py, build_gateway()
    parsers/                 # shopee.py, tiktok.py, generic.py, text.py, types.py, errors.py
  tests/                     # factories.py membuat PDF tiruan; test_parser_*/test_api/test_orders_service
frontend/src/
  api/client.js              # semua panggilan HTTP
  lib/format.js              # format Rupiah, label platform
  components/ui/             # Banner, Stat, Field, NumberInput, Combobox, Dropzone
  components/layout/         # Header
  features/converter/        # useConverter.js (state), ConverterPage, LinesTable, OrderInfoForm, ...
docs/                        # architecture.md, odoo-integration.md, ide-dan-garis-besar.md,
                             # quotations_import_template.xlsx (rujukan)
```

Aturan lapisan: `api/` hanya menerjemahkan HTTP; logika bisnis di `services/`; semua komunikasi ke
Odoo lewat `OdooGateway` di `integrations/odoo/`; parser tidak boleh tahu soal Odoo atau HTTP.

## Perintah

```bash
# Backend (dari backend/)
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
cp .env.example .env                                  # kosongkan ODOO_API_KEY = mode demo
uvicorn app.main:app --reload --port 8000
pytest                                                # semua tes
ruff check .                                          # lint

# Frontend (dari frontend/)
npm install
npm run dev                                           # http://localhost:5173, proxy /api -> :8000
npm run lint                                          # ESLint
npm run build                                         # vite build
```

Produksi: `npm run build`, lalu backend otomatis menyajikan `frontend/dist`.

## Konvensi

- Teks UI, pesan error API, dan komentar menjelaskan "kenapa" ditulis dalam **Bahasa Indonesia**.
  Nama kode (variabel, fungsi, tipe) dalam bahasa Inggris.
- Backend: type hint di fungsi publik, `ruff check` harus bersih, tidak ada logika bisnis di router.
- Frontend: JavaScript (ESM) dengan JSX, tanpa TypeScript; state dan efek samping di hook
  (`useConverter`), komponen presentasional menerima props. Panggilan HTTP hanya lewat
  `api/client.js`. Lint memakai ESLint (`frontend/eslint.config.js`): aturan bawaan + react-hooks,
  tanpa formatter — `npm run lint` harus bersih.
- `PLATFORM_LABEL` sengaja ada dua: `app/parsers/__init__.py` (peringatan API) dan
  `frontend/src/lib/format.js` (label UI). Bila menambah platform, ubah keduanya.
- Dropdown di dalam tabel memakai `position: fixed` (lihat `Combobox`) agar tidak terpotong
  `overflow-x-auto`. Jangan diganti ke `absolute`.

## Jangan lakukan

- Jangan commit `.env`, API key, atau PDF asli yang berisi data pelanggan. Untuk tes, buat PDF
  tiruan lewat `tests/factories.py`.
- Jangan mengubah `CSV_HEADER` tanpa menguji ke template/Odoo asli; urutan dan nama kolom harus
  persis. Pengecualian terverifikasi: `Order Reference` dihapus karena header kosong ditolak import.
- Jangan membuat parser menebak diam-diam saat data ambigu. Beri `warnings` ke pengguna.
- Jangan memakai XML-RPC/JSON-RPC Odoo atau menghubungi Odoo langsung dari browser.
- Jangan memakai akun admin Odoo untuk integrasi; gunakan user khusus dengan hak minimal.

## Menambah atau mengubah parser

1. Buat modul `parsers/<platform>.py` yang mengembalikan `ParsedDocument`.
2. Daftarkan di `PARSERS` dan `detect_platform` pada `parsers/__init__.py`.
3. Tambahkan pembuat PDF tiruan di `tests/factories.py` yang meniru tata letak asli, lalu tes untuk
   tiap pola (termasuk kasus tidak konsisten).
4. Jalankan `pytest` dan `ruff check .`.

## Definisi selesai

`pytest` hijau, `ruff check .` bersih, `npm run lint` dan `npm run build` berhasil, dan perubahan
perilaku parser disertai tes baru. Perubahan format/kolom Odoo juga memperbarui
`docs/odoo-integration.md`.

## Batasan yang diketahui

- Belum diuji terhadap Odoo 19 asli. Hal yang perlu diverifikasi: impor CSV Quotations
  (termasuk pemetaan kolom `Order Lines/Products/Database ID` ke subfield "Database ID").
- Parser Shopee dan TikTok baru diuji dengan PDF tiruan yang meniru tangkapan layar, belum dengan
  PDF asli. Cek dulu dengan PDF asli sebelum dipakai di produksi.
- Pencocokan produk Shopee sudah menyesuaikan struktur Odoo tim (nama template memuat ukuran,
  warna sebagai atribut varian), tapi **belum terverifikasi dengan contoh produk Odoo asli**:
  nama template, nilai atribut "Color"/"Warna", dan `import_attribute_values` harus dicek.
  Internal Reference varian sengaja tidak dipakai (masih kosong di Odoo).
- Satu PDF dengan banyak nomor pesanan menghasilkan banyak Sales Order dalam satu permintaan;
  belum ada penanganan gagal sebagian.
