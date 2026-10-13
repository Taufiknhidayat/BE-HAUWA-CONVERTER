from dataclasses import dataclass, field


@dataclass
class ParsedLine:
    name: str
    sku: str | None
    qty: float
    price: float = 0.0
    order_no: str | None = None
    # Nama produk (tanpa warna) dan bagian variasi (mis. "Maroon,L") dipisah di
    # parser agar pencocokan bisa menentukan template + warna di Odoo.
    product_name: str | None = None
    variant: str | None = None


@dataclass
class ParsedDocument:
    platform: str
    ref: str | None = None
    date: str | None = None  # YYYY-MM-DD
    lines: list[ParsedLine] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
