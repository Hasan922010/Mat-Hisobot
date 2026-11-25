"""Raqamli markirovka (Asl Belgisi / DataMatrix) kirim-chiqim va kamchiliklar dvigateli."""

import json
import re
from decimal import Decimal

_SPLIT_RE = re.compile(r"[,;\n\r|]+")
_GS1_DATAMATRIX_RE = re.compile(r"01\d{14}21")


def parse_marking_codes(raw) -> list[str]:
    """Xom katak qiymatidan unikal markirovka kodlari ro'yxatini ajratib oladi."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        items = [str(x).strip() for x in raw if str(x).strip()]
    else:
        text = str(raw).strip()
        if not text or text.lower() in ("nan", "none", "null", "-"):
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    items = [str(x).strip() for x in parsed if str(x).strip()]
                else:
                    items = [p.strip() for p in _SPLIT_RE.split(text) if p.strip()]
            except json.JSONDecodeError:
                items = [p.strip() for p in _SPLIT_RE.split(text) if p.strip()]
        elif _GS1_DATAMATRIX_RE.search(text):
            # Asl Belgisi GS1 DataMatrix kodlari probel/qator bilan ajraladi; ',' va ';' kod ichida keladi
            items = [p.strip() for p in text.split() if p.strip()]
        else:
            items = [p.strip() for p in _SPLIT_RE.split(text) if p.strip()]

    # Tartibni saqlagan holda dublikatlarni olib tashlash
    seen: set[str] = set()
    unique: list[str] = []
    for code in items:
        if code not in seen:
            seen.add(code)
            unique.append(code)
    return unique


def audit_marking_record(
    tovar_id: str,
    tovar_nomi_kirill: str,
    bosh_codes: list[str],
    kirim_tovar_soni: Decimal,
    kirim_codes: list[str],
    chiqim_tovar_soni: Decimal,
    chiqim_codes: list[str],
) -> dict:
    """
    Bitta tovar uchun markirovka qoldig'i va tafovutlarni hisoblaydi:
    - M_qoldiq = (M_bosh | M_kirim) - M_chiqim
    - Delta_kirim = |M_kirim| - Q_kirim
    - Delta_chiqim = |M_chiqim| - Q_chiqim
    - M_nomalum = M_chiqim - (M_bosh | M_kirim) (Ghost Marking)
    """
    bosh_set = set(bosh_codes)
    kirim_set = set(kirim_codes)
    chiqim_set = set(chiqim_codes)

    available_set = bosh_set | kirim_set
    qoldiq_codes = sorted(available_set - chiqim_set)
    noma_lum_codes = sorted(chiqim_set - available_set)

    kirim_farqi = Decimal(len(kirim_codes)) - kirim_tovar_soni
    chiqim_farqi = Decimal(len(chiqim_codes)) - chiqim_tovar_soni

    reasons: list[str] = []
    if kirim_farqi != 0:
        reasons.append(
            f"Kirim tafovuti: tovar soni ({kirim_tovar_soni}) va markirovka soni ({len(kirim_codes)}) mos emas (farq: {kirim_farqi:+})"
        )
    if chiqim_farqi != 0:
        reasons.append(
            f"Chiqim tafovuti: tovar soni ({chiqim_tovar_soni}) va markirovka soni ({len(chiqim_codes)}) mos emas (farq: {chiqim_farqi:+})"
        )
    if noma_lum_codes:
        reasons.append(
            f"Noma'lum markirovka sotuvi (Ghost Marking): {len(noma_lum_codes)} dona kirimda bo'lmagan kod sotilgan"
        )

    has_discrepancy = bool(reasons)

    return {
        "tovar_id": tovar_id,
        "tovar_nomi_kirill": tovar_nomi_kirill,
        "bosh_markirovka_soni": len(bosh_codes),
        "bosh_markirovkalar": bosh_codes,
        "kirim_tovar_soni": kirim_tovar_soni,
        "kirim_markirovka_soni": len(kirim_codes),
        "kirim_markirovkalar": kirim_codes,
        "chiqim_tovar_soni": chiqim_tovar_soni,
        "chiqim_markirovka_soni": len(chiqim_codes),
        "chiqim_markirovkalar": chiqim_codes,
        "qoldiq_markirovka_soni": len(qoldiq_codes),
        "qoldiq_markirovkalar": qoldiq_codes,
        "has_discrepancy": has_discrepancy,
        "kirim_farqi": kirim_farqi,
        "chiqim_farqi": chiqim_farqi,
        "noma_lum_chiqim_markirovkalar": noma_lum_codes,
        "kamchilik_sababi": "; ".join(reasons),
    }
