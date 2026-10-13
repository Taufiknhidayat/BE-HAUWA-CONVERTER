# Integrasi Odoo 19

## Autentikasi

1. Buat user khusus di Odoo (jangan admin) bila memakai mode Odoo. Hak minimal: baca Produk
   dan Kontak (untuk pencocokan dan combobox). Impor CSV Quotations dilakukan manual oleh
   admin lewat dialog import Odoo dengan haknya sendiri.
2. Login sebagai user itu → Preferences → Account Security → **New API Key**.
3. Isi `backend/.env`: `ODOO_URL`, `ODOO_DB`, `ODOO_API_KEY`. Kunci hanya disimpan di server.

Semua panggilan: `POST {ODOO_URL}/json/2/<model>/<method>` dengan header
`Authorization: bearer <API_KEY>` dan `X-Odoo-Database: <DB>`. XML-RPC dan JSON-RPC deprecated di
Odoo 19, jadi tidak dipakai.

## Pemetaan data

| Dari PDF / UI | Ke Odoo | Catatan |
|---|---|---|
| Kode Variasi (Shopee) / Seller SKU (TikTok) | `product.product.default_code` | Jalur pertama pencocokan (Shopee); lihat struktur produk di bawah |
| Nama Produk + Nama Variasi (warna) | `product.template` (nama) + atribut "Color"/"Warna" | Jalur kedua pencocokan Shopee saat `default_code` tidak ada/ambigu |
| Qty | `sale.order.line.product_uom_qty` | |
| Harga | `sale.order.line.price_unit` | Default `product.list_price`, bisa diedit |
| No Pesanan | `sale.order.client_order_ref` | Customer Reference = **nomor pesanan pertama** dari grup (Shopee: grup = produk; TikTok: grup = No. Pesanan) |
| Customer (dipilih) | `sale.order.partner_id` | Satu untuk seluruh PDF. Setelah parse, "Marketplace - Shopee"/"Marketplace - Tiktok" diisi otomatis bila ada di Odoo (`services/customers.py`) |
| Tanggal order | `sale.order.date_order` | Default: tanggal download PDF |

Pengelompokan baris menjadi Sales Order ada di `services/orders.group_orders` dan bergantung
platform: **Shopee satu Sales Order per produk** (PDF "Daftar Pesanan Per Produk" menulis banyak
No. Pesanan per produk tanpa memisahkan qty per nomor, jadi per produk = satu SO; nomor pesanan
pertama dipakai sebagai Customer Reference), **TikTok satu Sales Order per No. Pesanan**.
Opsi `split=false` menggabung semua baris menjadi satu SO. Frontend menampilkan baris
berkelompok per Sales Order dan mengirim `platform` di payload `/api/csv`.

## Struktur produk dan pencocokan

Di Odoo tim, **ukuran digabung ke nama template** (mis. "HAUWA Hijab - Medina Sporty L Bergo
Instan Melayu Plus Soft Inner") dan **warna adalah satu-satunya atribut varian**
(nilai `Color`/`Warna`). Varian (`product.product`) belum punya Internal Reference.

Pencocokan Shopee berjalan kaskade (langkah 2 adalah jalur utama selama `default_code` varian
kosong):

1. Kode Variasi PDF dicocokkan ke `default_code`. Kode yang cocok ke **lebih dari satu** produk
   tidak dipilih diam-diam (peringatan + pilih manual di tabel).
2. Bila langkah 1 tidak menghasilkan: nama produk dari PDF dicocokkan ke **nama template**
   (normalisasi huruf/spasi), lalu **warna dari Nama Variasi** (token sebelum tanda koma, mis.
   `Maroon` dari `Maroon,L`) dicocokkan case-insensitive ke nilai atribut varian **tanpa
   memedulikan spasi/hubung/underscore** (Shopee sering menulis `BrokenWhite`, TikTok/Odoo
   `Broken White`; keduanya dianggap sama agar master data tidak perlu diduplikasi hanya karena
   beda spasi). Diambil lewat
   `find_variants_by_template_names` (search `product.template` lalu `product.product` per
   template) dan `import_attribute_values` untuk membaca warna (`Color:Maroon` /
   `Color:Maroon,Size:L`).

Warna tidak ada / tidak ditemukan / cocok ke >1 varian → peringatan di response `/api/parse`;
pengguna memilih manual di tabel. Memilih diam-diam salah varian justru membuat Sales Order yang
salah. Pengecualian: template dengan **tepat satu** varian tetap dipilih otomatis walau warna PDF
tidak terbaca — itu satu-satunya pilihan yang pasti, bukan tebakan. Bila warna PDF terbaca tapi
tidak cocok dengan varian Odoo (mis. PDF `Green`, Odoo cuma punya `Black`) → **jangan auto-pick**;
baris dikosongkan dulu dan pengguna memilih manual di tabel lewat peringatan di response.
Ambiguitas nyata (>1 kandidat varian) tetap diserahkan ke manual. TikTok masih memakai `default_code` saja (cara baru menyusul).

## Template CSV (Quotations)

Urutan dan nama kolom mengikuti template Odoo 19, dengan satu penyimpangan yang disengaja pada
kolom produk (Database ID varian, lihat di bawah):

`Order Reference, Customer*, Order Date, Expiration, Payment Terms, Order Lines/Products/Database ID,
Order Lines/Quantity, Order Lines/Unit Price, Order Lines/Taxes, Sales Team, Customer Reference, Tags`

- Satu order dengan beberapa produk ditulis sebagai beberapa baris; kolom level order hanya diisi
  di baris pertama.
- `Order Reference` **tidak dicantumkan** di CSV. Kalau header-nya ikut tapi kosong, import Odoo
  menolak dengan "Missing Required value" (diverifikasi di Odoo 19); tanpa kolom itu, Odoo membuat
  nomor `S0000x` sendiri (memang otomatis).
- `Order Date` ditulis **`YYYY-MM-DD`** (mis. `2026-08-25`). Ini satu-satunya format teks yang
  selalu terdeteksi benar oleh import Odoo di semua bahasa; format lain (mis. `dd/mm/yyyy`)
  ditebak dari bahasa user dengan `%m/%d/%Y` di urutan pertama, sehingga `01/09/2026` bisa terbaca
  9 Januari (salah diam-diam) dan `25/08/2026` bisa ditolak. Ekspor Odoo sendiri memakai ISO.
- Qty dan Unit Price ditulis tanpa desimal berlebih, mengikuti sel `General` di template:
  `12` dan `1.98` (bukan `12.0`).
- Kolom produk memakai header `Order Lines/Products/Database ID` berisi **Database ID varian**
  (`product.id`). Ini menyimpang dari template resmi (`Order Lines/Products*` yang diisi nama),
  tetapi perlu: nama template sama untuk semua warna sehingga import by-name menemukan banyak
  match ("Found multiple matches") dan Odoo hanya memakai match pertama (bisa salah warna).
  Database ID unik per varian, jadi CSV selalu tepat varian tanpa mengubah data Odoo.
  Customer tetap dicocokkan lewat nama.

### Catatan saat mengimpor

- Nilai ISO tidak perlu mengubah **Date Format** di dialog import; deteksi otomatis Odoo selalu
  memakainya. Jangan buka dan simpan ulang CSV di Excel — Excel bisa mengubah tanggal ke format
  lokal dan merusak deteksi.
- Jangan ubah kolom `CSV_HEADER` tanpa menguji ke template/Odoo asli; format tanggal dan angka
  diatur terpisah lewat `_date_iso()` dan `_num()` di `services/orders.py`.
- Kolom `Order Lines/Products/Database ID` memakai referensi Database ID varian. Saat mengimpor,
  pastikan kolom itu terpetakan ke **Products / Database ID**; bila tidak otomatis, pilih subfield
  "Database ID" untuk kolom tersebut sekali di dialog impor. Database ID bersifat spesifik per
  instance Odoo (cukup, karena CSV diimpor ke instance yang sama).

## Yang belum diverifikasi

- Struktur produk di Odoo tim: SKU Shopee disimpan sebagai *Internal Reference* dan variasi sebagai
  *Attributes & Variants*. Pencocokan lewat `default_code` varian mungkin tidak berlaku; perlu
  disesuaikan setelah ada contoh produk asli. Internal Reference varian sengaja tidak dipakai
  (masih kosong di Odoo).
- Header `Order Lines/Products/Database ID` pada CSV Quotations belum diuji ke import Odoo 19 asli:
  perlu dipastikan kolom itu terpetakan ke subfield "Database ID" (bukan "Name") saat impor.
