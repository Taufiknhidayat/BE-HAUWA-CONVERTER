import re
from concurrent.futures import ThreadPoolExecutor

from ..integrations.odoo import OdooGateway
from ..parsers import ParsedDocument
from ..schemas import Line, ProductRef

# Token nama produk yang terlalu umum untuk dijadikan kata kunci pencarian: hanya
# mempersempit ke seri/varian produk yang tepat, bukan seluruh katalog.
_SEARCH_STOP = {
    'the', 'dan', 'yang', 'dari', 'untuk', 'dengan',
    'hijab', 'hauwa', 'haawa', 'haawam', 'plus', 'soft', 'inner',
    'jersey', 'rayon', 'series', 'sport', 'kids', 'anak',
    'melayu', 'bergo', 'instan', 'dailly',
}
# Auto-pilih via kemiripan nama hanya bila kandidat terbaik memenuhi ambang skor
# (Jaccard token) DAN unggul cukup jauh dari kandidat kedua. Selain itu manual.
_FUZZY_MIN_SCORE = 0.5
_FUZZY_MIN_MARGIN = 0.12


def _norm(value: str | None) -> str:
    """Normalisasi teks untuk perbandingan: huruf kecil, spasi dijajarkan."""
    return ' '.join((value or '').split()).casefold()


def _color_of(variant: str | None) -> str | None:
    """Token warna = bagian sebelum koma pertama dari Nama Variasi.

    Contoh: "Maroon,L" -> "Maroon", "Hitam" -> "Hitam".
    """
    if not variant:
        return None
    first = variant.split(',', 1)[0].strip()
    return first or None


def _color_key(value: str | None) -> str:
    """Kunci warna toleran: abaikan spasi/tanda hubung/underscore saat membandingkan.

    Shopee sering menggabungkan warna tanpa spasi ("BrokenWhite") sedangkan TikTok
    dan master Odoo memakai spasi ("Broken White"); keduanya harus dianggap sama.
    """
    if not value:
        return ''
    return re.sub(r'[^a-z0-9]', '', _norm(value))


def _edit_distance(a: str, b: str, limit: int) -> int:
    """Jarak Levenshtein dengan batas: bila pasti > limit langsung kembalikan
    limit+1 tanpa menghitung penuh (hemat untuk perbandingan banyak varian)."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        row_min = i
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            cur.append(v)
            if v < row_min:
                row_min = v
        if row_min > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def _color_close(color: str, candidate: str) -> bool:
    """Toleransi typo admin marketplace: beda 1 huruf (warna >= 4 huruf) atau
    2 huruf (warna >= 8 huruf). Contoh: 'Ligh Grey' -> 'Light Grey'."""
    a, b = _color_key(color), _color_key(candidate)
    if not a or not b or a == b:
        return False
    if min(len(a), len(b)) < 4:
        return False
    limit = 2 if min(len(a), len(b)) >= 8 else 1
    return _edit_distance(a, b, limit) <= limit


def _tokens(value: str) -> set[str]:
    return set(re.findall(r'[a-z0-9]+', _norm(value)))


def _search_terms(name: str, limit: int = 3) -> list[str]:
    """Kata kunci pencarian: token dari awal nama yang cukup khas (bukan stop
    word, >= 3 huruf). Contoh: '... Medina Instan L Bergo Melayu ...' -> ['medina']."""
    picked: list[str] = []
    for token in re.findall(r'[a-z0-9]+', _norm(name)):
        if token in _SEARCH_STOP or len(token) < 3:
            continue
        picked.append(token)
        if len(picked) >= limit:
            break
    if not picked:  # jaring pengaman: ambil token terpanjang
        picked = sorted(_tokens(name), key=len, reverse=True)[:limit]
    return picked


def _similarity(pdf_name: str, template_name: str) -> float:
    """Kemiripan nama berbasis Jaccard token (0..1)."""
    a, b = _tokens(pdf_name), _tokens(template_name)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _pick_unique_template(
    pdf_name: str, products: list[ProductRef]
) -> tuple[list[ProductRef] | None, list[str]]:
    """Pilih template dari kandidat lewat skor kemiripan nama.

    -> (varian template terpilih | None, daftar nama kandidat mirip). Auto-pilih
    hanya bila skor terbaik memenuhi ambang dan jelas unik (selisih cukup dengan
    kandidat kedua). Selain itu (None, kandidat) supaya dilaporkan sebagai manual.
    """
    groups: dict[str, list[ProductRef]] = {}
    for p in products:
        groups.setdefault(_norm(p.name), []).append(p)
    ranked = sorted(
        ((_similarity(pdf_name, name), name, variants)
         for name, variants in groups.items()),
        key=lambda item: item[0], reverse=True)
    if not ranked:
        return None, []
    best_score, _, best_variants = ranked[0]
    if best_score < _FUZZY_MIN_SCORE:
        return None, [name for _, name, _ in ranked[:3]]
    if len(ranked) == 1 or best_score - ranked[1][0] >= _FUZZY_MIN_MARGIN:
        return best_variants, []
    return None, [name for _, name, _ in ranked[:3]]


def _resolve_variant(
    variants: list[ProductRef], color: str | None, product_name: str, warnings: set[str]
) -> ProductRef | None:
    """Pilih varian sesuai warna; None + warning bila ambigu/tidak cocok.

    Template satu varian hanya dipilih otomatis bila warna PDF tidak terbaca/kosong
    atau cocok. Bila warna PDF ada tapi tidak cocok persis, dicoba toleransi typo
    (beda 1-2 huruf, mis. 'Ligh Grey' -> 'Light Grey'): hanya bila tepat satu
    kandidat yang dekat. Selain itu -> None + warning pilih manual (jangan menebak
    varian yang salah).
    """
    matched = ([p for p in variants if p.color and _color_key(p.color) == _color_key(color)]
               if color else [])
    if len(matched) == 1:
        return matched[0]
    if matched:
        warnings.add(f'Warna "{color}" untuk "{product_name}" cocok dengan beberapa '
                     'varian di Odoo; pilih manual di tabel.')
        return None
    if color:
        close = [p for p in variants if p.color and _color_close(color, p.color)]
        if len(close) == 1:
            warnings.add(f'Warna "{color}" mirip dengan "{close[0].color}" di Odoo '
                         '(mungkin typo); dipakai otomatis — periksa kembali.')
            return close[0]
        if close:
            names = ', '.join(sorted({p.color for p in close if p.color}))
            warnings.add(f'Warna "{color}" mirip dengan beberapa varian di Odoo '
                         f'({names}); pilih manual di tabel.')
            return None
    if len(variants) == 1:
        only = variants[0]
        if color:
            if not (only.color and _color_key(only.color) == _color_key(color)):
                avail = [only.color] if only.color else []
                detail = f' (tersedia: {", ".join(sorted(set(avail)))})' if avail else ''
                warnings.add(f'Warna "{color}" tidak ditemukan untuk "{product_name}" di Odoo{detail}; '
                             'pilih manual di tabel.')
                return None
        return only
    if not color:
        warnings.add(f'Produk "{product_name}" tidak memuat bagian warna di Nama Variasi; '
                     'pilih manual di tabel.')
        return None
    avail = sorted({p.color for p in variants if p.color})
    detail = f' (tersedia: {", ".join(avail)})' if avail else ''
    warnings.add(f'Warna "{color}" tidak ditemukan untuk "{product_name}" di Odoo{detail}; '
                 'pilih manual di tabel.')
    return None


def _fuzzy_variants(
    name: str, odoo: OdooGateway, already: list[ProductRef],
    cache: dict[str, list[ProductRef] | None], warnings: set[str],
    prefetched: list[ProductRef] | None = None,
) -> list[ProductRef] | None:
    """Fallback saat nama persis tidak ada: cari template mirip lewat kata kunci.

    Contoh nyata: PDF '... Medina Instan L Bergo Melayu ...' padahal template Odoo
    '... Medina Sporty L Bergo Instan Melayu ...' (urutan kata beda), atau 'Cutton'
    vs 'Cotton'. Auto-pilih hanya bila kandidat JELAS unik; kalau tidak, warning
    berisi kandidat mirip agar pengguna tinggal memilih.

    `prefetched` adalah hasil batch untuk banyak nama sekaligus (diambil lewat satu
    `find_variants_by_keywords`); disaring yang relevan untuk nama ini dengan aturan
    substring yang sama seperti pencarian `ilike` per-term di gateway, sehingga pool
    kandidat identik dengan panggilan per-nama. Tanpa itu (None), dipanggil per-nama.
    Kandidat yang namanya sama persis (setelah normalisasi) tetap dipertahankan:
    jalur exact bisa saja meleset karena gateway tidak mengembalikannya (mis. query
    ber-spasi ganda tidak cocok `ilike`), dan nama yang sama persis adalah kecocokan
    terbaik, bukan duplikat yang harus dibuang.
    """
    if name in cache:
        return cache[name]
    terms = _search_terms(name)
    if prefetched is None:
        fetched = odoo.find_variants_by_keywords(terms) if terms else []
    else:
        fetched = [p for p in prefetched
                   if terms and any(t in p.name.casefold() for t in terms)]
    pool = [*already, *fetched]
    chosen, similar = _pick_unique_template(name, pool)
    if chosen:
        cache[name] = chosen
        return chosen
    if similar:
        warnings.add(f'Produk "{name}" tidak cocok persis di Odoo; kandidat mirip: '
                     f'{", ".join(similar)} — pilih manual di tabel.')
    else:
        warnings.add(f'Produk "{name}" tidak ditemukan di Odoo; pilih manual di tabel.')
    cache[name] = None
    return None


def match_documents(
    docs: list[ParsedDocument], odoo: OdooGateway,
) -> list[tuple[list[Line], list[str]]]:
    """Cocokkan tiap baris tiap dokumen ke produk Odoo.

    Lookup Odoo (kode, nama template, kata kunci) dipakai bersama untuk seluruh
    dokumen dalam satu batch: satu RPC untuk banyak PDF yang produknya beririsan,
    bukan satu RPC per file. Hasil per dokumen: [(baris, peringatan), ...].

    Kaskade pencocokan (untuk Shopee; TikTok cukup lewat kode):
    1. Kode = Internal Reference (`default_code`) unik -> dipakai langsung.
    2. Bagi yang belum cocok, nama template + warna: produk Odoo punya nama template
       tanpa warna, warna hidup di atribut varian (Color/Warna). Baris yang belum
       cocok lalu dicocokkan lewat nama produk PDF (memuat ukuran) + token warna.

    Kode yang cocok ke lebih dari satu produk dianggap belum cocok (peringatan),
    kecuali langkah 2 bisa memastikan varian lewat warna. Template dengan **tepat
    satu** varian hanya dipilih otomatis bila warna PDF tidak terbaca/kosong atau
    cocok (termasuk toleransi typo 1-2 huruf yang unik); warna yang terbaca tapi
    tidak cocok diserahkan ke manual. Tidak ada tebakan diam-diam.

    Bila nama produk PDF tidak cocok persis dengan template Odoo (mis. urutan kata
    beda atau 'Cutton' vs 'Cotton'), dicoba kemiripan token; auto-pilih tetap hanya
    saat kandidat terbaik jelas unik, kalau tidak warning berisi kandidat mirip.
    """
    by_code: dict[str, ProductRef] = {}
    unresolved_codes: dict[str, list[ProductRef]] = {}

    # Dua pencarian independen jalan paralel (masing-masing bisa detik bila Odoo
    # lambat). Pencarian template memakai gabungan semua nama produk di seluruh
    # dokumen (superset dari yang akhirnya butuh) supaya tidak menunggu hasil
    # kode dulu; entri berlebih tidak dipakai jadi aman.
    skus = [ln.sku for doc in docs for ln in doc.lines if ln.sku]
    # Query pencarian dinormalisasi spasi (tanpa mengubah kapitalisasi): teks hasil
    # ekstraksi PDF bisa memuat spasi ganda yang membuat `ilike` Odoo meleset,
    # padahal template yang dicari sama. Hasilnya dirangkum lewat indeks
    # ternormalisasi di bawah sehingga kunci query tidak sensitif.
    names_all = [' '.join(n.split()) for n in dict.fromkeys(
        ln.product_name for doc in docs for ln in doc.lines if ln.product_name)]
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_codes = ex.submit(odoo.find_products_by_codes, skus) if skus else None
        fut_tmpl = (ex.submit(odoo.find_variants_by_template_names, names_all)
                    if names_all else None)
        candidates_by_code = fut_codes.result() if fut_codes else {}
        lookup = fut_tmpl.result() if fut_tmpl else {}
    for code, products in candidates_by_code.items():
        if len(products) == 1:
            by_code[code] = products[0]
        else:
            unresolved_codes[code] = products

    # Nama unik yang butuh fallback fuzzy dikumpulkan dulu; kata kuncinya diambil
    # dalam SATU panggilan (bukan 1 RPC per nama) lalu dipartisi per nama.
    # Pencocokan memakai kunci ternormalisasi (huruf/spasi): kunci dict `lookup`
    # adalah nama template apa adanya dari Odoo sehingga bisa beda kapitalisasi
    # dari nama di PDF ("Hauwa ..." vs "HAUWA ..."); `lookup.get(nama_mentah)`
    # langsung akan meleset dan template yang benar ikut terbuang di filter fuzzy
    # (nama yang `_norm`-nya sama dianggap sudah ditangani jalur exact).
    by_norm_name: dict[str, list[ProductRef]] = {}
    seen_ids: set[int] = set()
    for variants in lookup.values():
        for p in variants:
            if p.id in seen_ids:
                continue
            seen_ids.add(p.id)
            by_norm_name.setdefault(_norm(p.name), []).append(p)
    need_all = [ln for doc in docs for ln in doc.lines
                if ln.product_name and not (ln.sku and ln.sku in by_code)]
    exact: dict[str, list[ProductRef]] = {}
    pending: list[str] = []
    for ln in need_all:
        name = ln.product_name or ''
        normed = _norm(name)
        if normed not in exact:
            exact[normed] = list(by_norm_name.get(normed, []))
            if not exact[normed]:
                pending.append(name)
    terms_all = sorted({t for n in pending for t in _search_terms(n)})
    prefetched = odoo.find_variants_by_keywords(terms_all) if terms_all else []

    by_name: dict[tuple[str, str], ProductRef] = {}
    name_warnings: set[str] = set()
    fuzzy_cache: dict[str, list[ProductRef] | None] = {}
    for ln in need_all:
        color = _color_of(ln.variant)
        name = ln.product_name or ''
        key = (_norm(name), color or '')
        if key in by_name:
            continue
        candidates = exact[_norm(name)]
        if not candidates:
            variants = _fuzzy_variants(name, odoo, by_norm_name.get(_norm(name), []),
                                       fuzzy_cache, name_warnings, prefetched)
            if not variants:
                continue
            candidates = variants
        pick = _resolve_variant(candidates, color, name, name_warnings)
        if pick:
            by_name[key] = pick

    results: list[tuple[list[Line], list[str]]] = []
    for doc in docs:
        warnings = sorted(name_warnings)
        for code, products in unresolved_codes.items():
            already_matched = any(
                ln.sku == code
                and (_norm(ln.product_name or ''), _color_of(ln.variant) or '') in by_name
                for ln in doc.lines
            )
            if already_matched:
                continue
            names = ', '.join(p.name for p in products)
            warnings.append(
                f'SKU "{code}" cocok dengan {len(products)} produk Odoo ({names}); '
                'baris ditandai belum cocok — pilih manual di tabel.'
            )

        lines = []
        for ln in doc.lines:
            product = by_code.get(ln.sku) if ln.sku else None
            if product is None and ln.product_name:
                product = by_name.get((_norm(ln.product_name), _color_of(ln.variant) or ''))
            lines.append(Line(
                name=ln.name, sku=ln.sku, qty=ln.qty,
                price=ln.price or (product.price if product else 0),
                order_no=ln.order_no, product=product,
                product_name=ln.product_name, variant=ln.variant,
            ))
        results.append((lines, warnings))
    return results


def match_lines(doc: ParsedDocument, odoo: OdooGateway) -> tuple[list[Line], list[str]]:
    """Cocokkan tiap baris satu dokumen ke produk Odoo (bungkus match_documents)."""
    return match_documents([doc], odoo)[0]