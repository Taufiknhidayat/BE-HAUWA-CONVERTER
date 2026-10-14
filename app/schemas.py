"""Skema request/response API."""
from pydantic import BaseModel


class ProductRef(BaseModel):
    id: int
    name: str
    code: str | None = None
    price: float = 0  # Sales Price di Odoo
    color: str | None = None  # nilai atribut Color/Warna (varian)
    # Pajak penjualan produk: nama (taxes, untuk keterbacaan) dan ID mentah
    # (tax_ids, untuk kolom Taxes di CSV). Nama pajak bisa kembar di Odoo
    # (mis. Sales vs Purchase) sehingga CSV memakai ID yang unik per record.
    # Keduanya kosong bila produk tidak punya pajak.
    taxes: list[str] = []
    tax_ids: list[int] = []


class Customer(BaseModel):
    id: int
    name: str


class Line(BaseModel):
    name: str
    sku: str | None = None
    qty: float = 1
    price: float = 0
    order_no: str | None = None
    product: ProductRef | None = None
    # Nama produk di PDF (tanpa warna) — dipakai untuk mengelompokkan satu
    # Sales Order per produk di Shopee.
    product_name: str | None = None
    # Varian (warna) di PDF — tambahan informasi; sudah tertanam di `name`.
    variant: str | None = None
    # Nama file PDF asal baris ini (hasil batch banyak PDF); diabaikan saat CSV.
    source_file: str | None = None


class ParseResult(BaseModel):
    platform: str
    order_ref: str | None = None
    order_date: str | None = None
    lines: list[Line]
    warnings: list[str] = []
    customer: Customer | None = None  # customer marketplace yang cocok dengan platform


class FileFailure(BaseModel):
    # Satu file dalam batch yang dilewati beserta alasannya.
    file: str
    error: str


class BatchParseResult(ParseResult):
    # Hasil penggabungan banyak PDF: daftar nama file yang BERHASIL diproses,
    # nama file yang disarankan untuk payload CSV (`file_name` di SubmitIn),
    # dan file yang dilewati beserta alasannya (batch tidak atomik: satu file
    # gagal tidak membatalkan file lain).
    files: list[str] = []
    file_name: str | None = None
    failed: list[FileFailure] = []


class SubmitIn(BaseModel):
    customer_name: str | None = None
    order_ref: str | None = None  # dipakai kalau split=False
    order_date: str | None = None
    platform: str | None = None  # 'shopee'/'tiktok' — menentukan aturan pengelompokan
    split: bool = True  # True: satu grup (No Pesanan / produk) = satu Sales Order
    file_name: str | None = None  # nama file PDF sumber — untuk nama file CSV
    session: str | None = None  # sesi unduhan ('1'/'2'/'3') — untuk nama file CSV
    lines: list[Line]


class Health(BaseModel):
    mode: str  # 'mock' | 'odoo'
    connected: bool
    detail: str
