class ParseError(Exception):
    """Dasar semua kegagalan membaca dokumen."""


class UnknownPlatformError(ParseError):
    pass


class PlatformMismatchError(ParseError):
    """Platform pilihan pengguna bertentangan dengan hasil deteksi isi PDF."""


class EmptyDocumentError(ParseError):
    pass
