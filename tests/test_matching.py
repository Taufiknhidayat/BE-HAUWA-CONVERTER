from app.parsers.types import ParsedDocument, ParsedLine
from app.schemas import ProductRef
from app.services.matching import match_lines


class _FakeGateway:
    """Gateway tiruan: kandidat per kode dan per nama template ditentukan di awal."""

    def __init__(self, codes=None, templates=None):
        self._codes = codes or {}
        self._templates = templates or {}

    def find_products_by_codes(self, codes):
        return {c: self._codes[c] for c in set(codes) if c in self._codes}

    def find_variants_by_template_names(self, names):
        out = {}
        for n in dict.fromkeys(names):
            out[n] = [p for name, ps in self._templates.items() if name == n for p in ps]
        return out

    def find_variants_by_keywords(self, terms):
        wanted = [t.casefold() for t in terms if t]
        out = []
        for name, ps in self._templates.items():
            if any(t in name.casefold() for t in wanted):
                out.extend(ps)
        return out


def _doc(*skus):
    lines = [ParsedLine(name=f'Baris {s}', sku=s, qty=1) for s in skus]
    return ParsedDocument(platform='shopee', lines=lines)


def _name_doc(*items):
    """items: [(product_name, variant, sku|None), ...] -> dokumen Shopee."""
    lines = []
    for name, variant, sku in items:
        display = f'{name} - {variant}' if variant else name
        lines.append(ParsedLine(name=display, sku=sku, qty=1,
                                product_name=name, variant=variant))
    return ParsedDocument(platform='shopee', lines=lines)


def test_unique_code_is_matched():
    p = ProductRef(id=1, name='Satu', code='A', price=1000)
    lines, warnings = match_lines(_doc('A', 'B'), _FakeGateway(codes={'A': [p]}))
    assert [ln.product for ln in lines] == [p, None]
    assert warnings == []


def test_code_matches_by_default_code_when_both_present():
    by_code = ProductRef(id=1, name='Raya', code='R-1', price=75000)
    by_name = ProductRef(id=2, name='Raya', color='Maroon', price=80000)
    lines, _ = match_lines(
        _name_doc(('Raya', 'Maroon', 'R-1')),
        _FakeGateway(codes={'R-1': [by_code]}, templates={'Raya': [by_name]}))
    assert lines[0].product == by_code  # kode lebih spesifik, menang


def test_duplicate_code_is_left_unmatched_with_warning():
    a = ProductRef(id=1, name='Varian Merah', code='A', price=1000)
    b = ProductRef(id=2, name='Varian Biru', code='A', price=1000)
    lines, warnings = match_lines(_doc('A'), _FakeGateway(codes={'A': [a, b]}))
    assert lines[0].product is None  # jangan menebak varian
    assert len(warnings) == 1
    assert 'SKU "A"' in warnings[0]
    assert '2 produk Odoo' in warnings[0]
    assert 'Varian Merah' in warnings[0] and 'Varian Biru' in warnings[0]


def test_empty_sku_matches_by_template_name_and_color():
    templates = {
        'HAUWA Hijab - Raya Bergo Melayu Bandana Sport S': [
            ProductRef(id=1, name='HAUWA Hijab - Raya Bergo Melayu Bandana Sport S',
                       color='Maroon', price=75000),
            ProductRef(id=2, name='HAUWA Hijab - Raya Bergo Melayu Bandana Sport S',
                       color='Black', price=75000),
        ],
    }
    lines, warnings = match_lines(
        _name_doc(('HAUWA Hijab - Raya Bergo Melayu Bandana Sport S', 'Maroon,L', None)),
        _FakeGateway(templates=templates))
    assert lines[0].product == templates['HAUWA Hijab - Raya Bergo Melayu Bandana Sport S'][0]
    assert lines[0].price == 75000
    assert warnings == []


def test_duplicate_sku_is_resolved_by_color_when_template_known():
    a = ProductRef(id=1, name='Raya', color='Maroon', price=75000)
    b = ProductRef(id=2, name='Raya', color='Black', price=75000)
    lines, warnings = match_lines(
        _name_doc(('Raya', 'Black', 'X')),
        _FakeGateway(codes={'X': [a, b]}, templates={'Raya': [a, b]}))
    # SKU ganda diselesaikan lewat warna, tanpa peringatan
    assert lines[0].product == b
    assert warnings == []


def test_wrong_color_warns_and_lists_available_colors():
    templates = {
        'Raya': [ProductRef(id=1, name='Raya', color='Maroon', price=75000),
                 ProductRef(id=2, name='Raya', color='Black', price=75000)],
    }
    lines, warnings = match_lines(
        _name_doc(('Raya', 'Pink', None)), _FakeGateway(templates=templates))
    assert lines[0].product is None
    assert any('Warna "Pink"' in w and 'Maroon' in w and 'Black' in w for w in warnings)


def test_unknown_template_warns():
    lines, warnings = match_lines(
        _name_doc(('Produk Baru', 'Maroon', None)), _FakeGateway())
    assert lines[0].product is None
    assert any('tidak ditemukan di Odoo' in w for w in warnings)


def test_ambiguous_when_multiple_variants_share_the_color():
    # Data rusak (warna sama untuk 2 varian) -> jangan menebak, beri peringatan.
    duplicates = [
        ProductRef(id=1, name='Ganda', color='Maroon', price=1),
        ProductRef(id=2, name='Ganda', color='Black', price=1),
        ProductRef(id=3, name='Ganda', color='Maroon', price=2),
    ]
    lines, warnings = match_lines(
        _name_doc(('Ganda', 'Maroon', None)),
        _FakeGateway(templates={'Ganda': duplicates}))
    assert lines[0].product is None
    assert any('cocok dengan beberapa varian' in w for w in warnings)


def test_unknown_and_missing_sku_stay_unmatched_without_warning():
    lines, warnings = match_lines(_doc('TIDAK-ADA', None), _FakeGateway())
    assert all(ln.product is None for ln in lines)
    assert warnings == []


def test_single_candidate_matches_even_without_color():
    """Template hanya punya satu varian dan warna PDF tidak terbaca -> satu-satunya
    pilihan yang pasti, otomatis tanpa peringatan."""
    solo = ProductRef(id=1, name='Solo', color='Black', price=50000)
    lines, warnings = match_lines(
        _name_doc(('Solo', None, None)), _FakeGateway(templates={'Solo': [solo]}))
    assert lines[0].product == solo
    assert lines[0].price == 50000
    assert warnings == []


def test_single_candidate_matches_wrong_color_with_warning():
    """Satu varian tapi warna PDF tak cocok: warna ada di PDF tapi tidak cocok ->
    jangan menebak; kosongkan dulu agar user pilih manual."""
    solo = ProductRef(id=1, name='Solo', color='Black', price=50000)
    lines, warnings = match_lines(
        _name_doc(('Solo', 'Pink', None)), _FakeGateway(templates={'Solo': [solo]}))
    assert lines[0].product is None
    assert lines[0].price == 0  # belum cocok
    assert any('Warna "Pink"' in w and 'Black' in w and 'pilih manual' in w for w in warnings)


def test_multiple_candidates_missing_color_still_manual():
    """Warna tidak terbaca dan template punya >1 varian -> ambiguitas nyata,
    tetap minta pilih manual."""
    a = ProductRef(id=1, name='Ganda', color='Maroon', price=1)
    b = ProductRef(id=2, name='Ganda', color='Black', price=1)
    lines, warnings = match_lines(
        _name_doc(('Ganda', None, None)), _FakeGateway(templates={'Ganda': [a, b]}))
    assert lines[0].product is None
    assert any('tidak memuat bagian warna' in w and 'pilih manual' in w for w in warnings)


def test_fuzzy_matches_template_with_reordered_name():
    """Nama PDF bisa beda urutan kata dari template Odoo (antaraja 2: PDF
    'Instan L Bergo Melayu' padahal Odoo 'Sporty L Bergo Instan Melayu').
    Kemiripan token memilih template yang benar secara otomatis selama jelas unik."""
    pdf_name = 'HAUWA Hijab - Medina Instan L Bergo Melayu Plus Soft Inner'
    sporty_l = ProductRef(
        id=10, name='HAUWA Hijab - Medina Sporty L Bergo Instan Melayu Plus Soft Inner',
        color='Burgundy', price=89000)
    sporty_l_hitam = ProductRef(
        id=11, name='HAUWA Hijab - Medina Sporty L Bergo Instan Melayu Plus Soft Inner',
        color='Hitam', price=89000)
    sporty_s = ProductRef(
        id=20, name='HAUWA Hijab - Medina Sporty S Bergo Instan Melayu Plus Soft Inner',
        color='Hitam', price=89000)
    templates = {sporty_l.name: [sporty_l, sporty_l_hitam], sporty_s.name: [sporty_s]}
    lines, warnings = match_lines(
        _name_doc((pdf_name, 'Burgundy,L', None)), _FakeGateway(templates=templates))
    assert lines[0].product == sporty_l  # template 'L', bukan 'S'
    assert warnings == []


def test_fuzzy_matches_template_with_misspelled_word():
    """Salah ketik di PDF ('Cutton' vs 'Cotton'): kandidat unik tetap dipilih otomatis."""
    pdf_name = 'HAUWA Hijab - Iris Segitiga Bandana melayu Cutton cooltech'
    taupe = ProductRef(id=30, name='HAUWA Hijab - Iris Segitiga Bandana melayu Cotton cooltech',
                       color='Taupe', price=65000)
    black = ProductRef(id=31, name='HAUWA Hijab - Iris Segitiga Bandana melayu Cotton cooltech',
                       color='Black', price=65000)
    lines, warnings = match_lines(
        _name_doc((pdf_name, 'Taupe', None)), _FakeGateway(templates={taupe.name: [taupe, black]}))
    assert lines[0].product == taupe
    assert warnings == []


def test_fuzzy_ambiguous_lists_candidates_for_manual():
    """Dua kandidat mirip dengan skor sama -> jangan menebak; warning sebutkan
    kandidatnya supaya tinggal dipilih manual."""
    pdf_name = 'HAUWA Hijab - Ganda Sport Bergo Melayu'
    a = ProductRef(id=1, name='HAUWA Hijab - Ganda Sport Bergo Melayu Bandana',
                   color='Black', price=1)
    b = ProductRef(id=2, name='HAUWA Hijab - Ganda Sport Bergo Melayu Instan',
                   color='Black', price=1)
    lines, warnings = match_lines(
        _name_doc((pdf_name, 'Black', None)),
        _FakeGateway(templates={a.name: [a], b.name: [b]}))
    assert lines[0].product is None
    assert any('kandidat mirip' in w and 'bandana' in w and 'instan' in w for w in warnings)


def test_fuzzy_below_threshold_stays_manual():
    """Kandidat yang muncul dari kata kunci tapi miripnya lemah -> tidak dipaksa
    cocok, tetap manual."""
    pdf_name = 'HAUWA Hijab - Alfa Beta Gamma Delta Epsilon'
    far = ProductRef(id=1, name='HAUWA Hijab - Alfa Zeta Eta Theta Iota',
                     color='Black', price=1)
    lines, warnings = match_lines(
        _name_doc((pdf_name, 'Black', None)), _FakeGateway(templates={far.name: [far]}))
    assert lines[0].product is None
    assert any('pilih manual' in w for w in warnings)


def test_color_tolerates_missing_space():
    """Shopee menulis 'BrokenWhite' sementara Odoo/TikTok 'Broken White': tetap cocok
    tanpa memaksa duplikat master data hanya karena beda spasi."""
    templates = {
        'Raya': [
            ProductRef(id=1, name='Raya', color='Broken White', price=75000),
            ProductRef(id=2, name='Raya', color='Black', price=75000),
        ],
    }
    lines, warnings = match_lines(
        _name_doc(('Raya', 'BrokenWhite', None)), _FakeGateway(templates=templates))
    assert lines[0].product == templates['Raya'][0]
    assert warnings == []


def test_color_tolerates_dash_and_underscore():
    """Pemisah warna (spasi/hubung/underscore) diabaikan saat membandingkan."""
    templates = {
        'Raya': [
            ProductRef(id=1, name='Raya', color='Navy Blue', price=75000),
            ProductRef(id=2, name='Raya', color='Black', price=75000),
        ],
    }
    lines, warnings = match_lines(
        _name_doc(('Raya', 'Navy-Blue,L', None)), _FakeGateway(templates=templates))
    assert lines[0].product == templates['Raya'][0]
    assert warnings == []


def test_single_candidate_spacing_difference_has_no_warning():
    """Varian tunggal dengan warna beda spasi dianggap cocok, bukan 'warna tidak ada'."""
    solo = ProductRef(id=1, name='Solo', color='Broken White', price=50000)
    lines, warnings = match_lines(
        _name_doc(('Solo', 'BrokenWhite', None)), _FakeGateway(templates={'Solo': [solo]}))
    assert lines[0].product == solo
    assert warnings == []


def test_fuzzy_batches_keywords_into_single_call():
    """Dua nama butuh fallback fuzzy -> kata kunci diambil dalam 1 panggilan
    (bukan 1 RPC per nama), dan tiap nama tetap cocok ke template yang tepat."""
    size_l = ProductRef(
        id=10, name='HAUWA Hijab - Medina Sporty L Bergo Instan Melayu Plus Soft Inner',
        color='Hitam', price=89000)
    size_s = ProductRef(
        id=20, name='HAUWA Hijab - Medina Sporty S Bergo Instan Melayu Plus Soft Inner',
        color='Hitam', price=89000)

    class CountingGateway(_FakeGateway):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.keyword_calls = []

        def find_variants_by_keywords(self, terms):
            self.keyword_calls.append(list(terms))
            return super().find_variants_by_keywords(terms)

    gw = CountingGateway(templates={size_l.name: [size_l], size_s.name: [size_s]})
    doc = _name_doc(
        ('HAUWA Hijab - Medina Instan L Bergo Melayu Plus Soft Inner', 'Hitam', None),
        ('HAUWA Hijab - Medina Instan S Bergo Melayu Plus Soft Inner', 'Hitam', None))
    lines, warnings = match_lines(doc, gw)
    assert len(gw.keyword_calls) == 1  # batch, bukan 2 panggilan
    assert lines[0].product == size_l
    assert lines[1].product == size_s
    assert warnings == []


def test_color_typo_matches_unique_close_candidate():
    """Kasus nyata: PDF 'Ligh Grey' (typo, kurang 't') cocok ke 'Light Grey' di
    Odoo tanpa mengorbankan kandidat lain ('Grey' tetap tidak cocok)."""
    templates = {
        'Itsnan - Casual Bergo Instan Melayu rayon': [
            ProductRef(id=1, name='Itsnan - Casual Bergo Instan Melayu rayon',
                       color='Black', price=89000),
            ProductRef(id=2, name='Itsnan - Casual Bergo Instan Melayu rayon',
                       color='Broken White', price=89000),
            ProductRef(id=3, name='Itsnan - Casual Bergo Instan Melayu rayon',
                       color='Grey', price=89000),
            ProductRef(id=4, name='Itsnan - Casual Bergo Instan Melayu rayon',
                       color='Light Grey', price=89000),
            ProductRef(id=5, name='Itsnan - Casual Bergo Instan Melayu rayon',
                       color='Taupe', price=89000),
        ],
    }
    name = 'Itsnan - Casual Bergo Instan Melayu rayon'
    lines, warnings = match_lines(
        _name_doc((name, 'Ligh Grey', None)), _FakeGateway(templates=templates))
    assert lines[0].product == templates[name][3]
    assert any('Ligh Grey' in w and 'Light Grey' in w and 'typo' in w for w in warnings)
    assert not any('pilih manual' in w for w in warnings)


def test_color_typo_single_variant_matches():
    """Varian tunggal + typo 1 huruf ('Blak' -> 'Black'): otomatis + warning typo."""
    solo = ProductRef(id=1, name='Solo', color='Black', price=50000)
    lines, warnings = match_lines(
        _name_doc(('Solo', 'Blak', None)), _FakeGateway(templates={'Solo': [solo]}))
    assert lines[0].product == solo
    assert any('Blak' in w and 'Black' in w and 'typo' in w for w in warnings)


def test_color_typo_ambiguous_stays_manual():
    """Typo dekat ke >1 varian ('Marron' vs 'Maroon' dan 'Marroon') -> manual."""
    templates = {
        'Raya': [
            ProductRef(id=1, name='Raya', color='Maroon', price=75000),
            ProductRef(id=2, name='Raya', color='Marroon', price=75000),
        ],
    }
    lines, warnings = match_lines(
        _name_doc(('Raya', 'Marron', None)), _FakeGateway(templates=templates))
    assert lines[0].product is None
    assert any('mirip dengan beberapa varian' in w and 'pilih manual' in w for w in warnings)


class _OdooStyleGateway(_FakeGateway):
    """Meniru OdooClient asli: hasil find_variants_by_template_names dikunci
    nama template apa adanya dari Odoo (bukan nama yang diminta), dengan
    pencarian `ilike` yang case-insensitive. Inilah yang dulu membuat beda
    kapitalisasi ("Hauwa" vs "HAUWA") gagal cocok padahal mock lolos."""

    def find_variants_by_template_names(self, names):
        wanted = [n for n in dict.fromkeys(names) if n]
        out = {}
        for odoo_name, ps in self._templates.items():
            if any(n.casefold() in odoo_name.casefold() for n in wanted):
                out[odoo_name] = list(ps)
        return out


def _iris_templates(
    odoo_name='HAUWA Hijab - Iris Segitiga Bandana melayu Cutton cooltech',
):
    return {odoo_name: [
        ProductRef(id=40, name=odoo_name, color='Black', price=65000),
        ProductRef(id=41, name=odoo_name, color='Taupe', price=65000),
    ]}


def test_template_name_ignores_case_difference():
    """Regresi kasus nyata: PDF TikTok 'Hauwa ...' vs Odoo 'HAUWA ...' harus
    cocok ke varian Black yang tepat (dulu gagal karena kunci lookup mentah,
    lalu template yang benar ikut terbuang di filter fuzzy)."""
    templates = _iris_templates()
    odoo_name = next(iter(templates))
    lines, warnings = match_lines(
        _name_doc((odoo_name.replace('HAUWA', 'Hauwa'), 'Black', None)),
        _OdooStyleGateway(templates=templates))
    assert lines[0].product == templates[odoo_name][0]
    assert warnings == []


def test_template_name_ignores_case_difference_reversed():
    """Arah sebaliknya juga harus cocok: PDF 'HAUWA ...' vs Odoo 'Hauwa ...'
    (kasus Shopee setelah rename kemarin)."""
    odoo_name = 'Hauwa Hijab - Iris Segitiga Bandana melayu Cutton cooltech'
    templates = _iris_templates(odoo_name)
    lines, warnings = match_lines(
        _name_doc((odoo_name.replace('Hauwa', 'HAUWA'), 'Black', None)),
        _OdooStyleGateway(templates=templates))
    assert lines[0].product == templates[odoo_name][0]
    assert warnings == []


def test_template_name_ignores_extra_spaces():
    """Spasi ganda di PDF tetap cocok ke template Odoo yang sama."""
    templates = _iris_templates()
    odoo_name = next(iter(templates))
    pdf_name = odoo_name.replace('Hauwa Hijab', 'Hauwa  Hijab').replace('HAUWA Hijab', 'HAUWA  Hijab')
    lines, warnings = match_lines(
        _name_doc((pdf_name, 'Taupe', None)),
        _OdooStyleGateway(templates=templates))
    assert lines[0].product == templates[odoo_name][1]
    assert warnings == []
