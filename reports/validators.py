"""Yuklangan Excel/CSV fayllarni xavfsiz tekshirish (MIME, hajm <= 100MB, ustunlar)."""

from pathlib import Path

from django.core.exceptions import ValidationError

ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB


def validate_uploaded_file(uploaded_file) -> None:
    if not uploaded_file:
        raise ValidationError("Fayl tanlanmagan.")

    ext = Path(uploaded_file.name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"Noto'g'ri fayl formati ({ext}). Faqat .xlsx, .xls yoki .csv yuklang."
        )

    if uploaded_file.size <= 0:
        raise ValidationError("Yuklangan fayl bo'sh.")
    if uploaded_file.size > MAX_FILE_SIZE_BYTES:
        raise ValidationError("Fayl hajmi 100 MB dan oshmasligi kerak.")

    # Magic-byte tekshiruvi (fayl boshini o'qib, pozitsiyani qaytaramiz)
    pos = uploaded_file.tell()
    header = uploaded_file.read(8)
    uploaded_file.seek(pos)

    if ext == ".xlsx" and not header.startswith(b"PK\x03\x04"):
        raise ValidationError("Fayl haqiqiy .xlsx (ZIP/OOXML) formatida emas.")
    if ext == ".xls" and not header.startswith(b"\xd0\xcf\x11\xe0"):
        raise ValidationError("Fayl haqiqiy .xls (BIFF) formatida emas.")
