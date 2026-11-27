class BistScannerError(Exception):
    """Uygulama temel hata sınıfı."""


class DataFetchError(BistScannerError):
    """Dış veri kaynağından veri çekilemediğinde fırlatılır."""


class ValidationError(BistScannerError):
    """Kullanıcı girdisi veya iş kuralı doğrulama hatası."""
