"""Pandas/NumPy vektorlashgan Svod va hisob-kitob dvigateli (1M+ qator himoyasi)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Callable

import numpy as np
import openpyxl
import pandas as pd

from .fuzzy_matcher import deduplicate_names
from .marking_engine import audit_marking_record, parse_marking_codes
from .transliterator import latin_to_cyrillic

CHUNK_SIZE = 50_000

HEADER_ALIASES: dict[str, list[str]] = {
    "tovar_id": ["mxik", "мхик", "ikpu", "икпу", "tovar_id", "kod", "код", "barkod", "sku", "артикул", "id"],
    "tovar_nomi": [
        "примечание_к_товару_работе_услуге",
        "примечание_к_товару",
        "наименование_товара",
        "tovar_nomi",
        "tovar",
        "nomi",
        "mahsulot",
        "наименование",
        "товар",
        "номенклатура",
    ],
    "birligi": ["birligi", "olchov_birligi", "olchov", "единица_измерения", "ед_изм", "единица", "ед"],
    "bosh_qoldiq_soni": ["boshlangich_qoldiq", "bosh_qoldiq", "bosh_qoldiq_soni", "нач_остаток", "начальный_остаток"],
    "kirim_soni": ["kirim", "kirim_miqdori", "kirim_soni", "prikhod", "приход", "поступление"],
    "chiqim_soni": ["chiqim", "chiqim_miqdori", "chiqim_soni", "rasxod", "sotuv", "расход", "продажа", "реализация"],
    "quantity": ["miqdor", "soni", "kolichestvo", "количество", "кол_во", "qty"],
    "summa": [
        "стоимость_поставки_с_учётом_ндс",
        "стоимость_поставки_с_учетом_ндс",
        "стоимость_поставки",
        "summa",
        "jami_summa",
        "kirim_summa",
        "chiqim_summa",
        "сумма",
        "стоимость",
        "всего",
    ],
    "ortacha_narx": ["narx", "tannarx", "ortacha_narx", "цена", "себестоимость"],
    "bosh_markirovka": ["bosh_markirovka", "boshlangich_markirovka", "нач_киз", "нач_маркировка"],
    "kirim_markirovka": ["kirim_markirovka", "prikhod_markirovka", "приход_киз", "приход_маркировка"],
    "chiqim_markirovka": ["chiqim_markirovka", "sotuv_markirovka", "расход_киз", "расход_маркировка"],
    "markirovka": ["маркировка", "markirovka", "киз", "datamatrix", "sgtin"],
}

_HEADER_EXCLUSIONS: dict[str, tuple[str, ...]] = {
    "tovar_nomi": ("продавец", "покупатель", "контрагент", "филиал"),
    "summa": ("акциз", "ндс_сумма", "сумма_ндс"),
}

_NON_NUM_RE = re.compile(r"[^\d.\-]")


def clean_decimal(value, places: int = 2) -> Decimal:
    """
    Decimal Guard: nuqtani (.) hech qachon o'chirmaydi!
    Vergulni (,) nuqtaga almashtiradi va berilgan aniqlikda Decimal qaytaradi.
    """
    quant = Decimal(10) ** -places
    if value is None:
        return Decimal("0").quantize(quant)
    if isinstance(value, Decimal):
        return value.quantize(quant, rounding=ROUND_HALF_UP)
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return Decimal("0").quantize(quant)
        return Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP)

    text = str(value).strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    text = _NON_NUM_RE.sub("", text)
    if not text or text in ("-", "."):
        return Decimal("0").quantize(quant)
    # Agar bir nechta nuqta bo'lsa, faqat oxirgisini kasr ajratuvchi sifatida qoldiramiz
    if text.count(".") > 1:
        parts = text.split(".")
        text = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return Decimal(text).quantize(quant, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return Decimal("0").quantize(quant)


def _normalize_header(col: object) -> str:
    text = str(col or "").strip().lower()
    text = re.sub(r"[\s\-\/]+", "_", text)
    text = re.sub(r"['‘’`\"()]+", "", text)
    return text.strip("_")


def map_headers(columns: list[object]) -> dict[str, str]:
    """Fayl ustunlarini kanonik maydon nomlariga moslashtiradi (avval aniq, keyin qisman)."""
    normalized = {_normalize_header(c): str(c) for c in columns if c is not None and str(c).strip()}
    mapping: dict[str, str] = {}
    used_cols: set[str] = set()

    # 1-bosqich: Barcha maydonlar uchun to'g'ridan-to'g'ri aniq moslik
    for canonical, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            norm_alias = _normalize_header(alias)
            if norm_alias in normalized and normalized[norm_alias] not in used_cols:
                mapping[canonical] = normalized[norm_alias]
                used_cols.add(normalized[norm_alias])
                break

    # 2-bosqich: Qolgan maydonlar uchun qisman moslik (qisqa <=3 harfli aliaslar faqat alohida so'z sifatida)
    for canonical, aliases in HEADER_ALIASES.items():
        if canonical in mapping:
            continue
        excluded_words = _HEADER_EXCLUSIONS.get(canonical, ())
        for norm_col, orig_col in normalized.items():
            if orig_col in used_cols:
                continue
            if excluded_words and any(ex in norm_col for ex in excluded_words):
                continue
            tokens = set(norm_col.split("_"))
            matched = False
            for a in aliases:
                na = _normalize_header(a)
                if len(na) >= 4:
                    if na in norm_col:
                        matched = True
                        break
                elif na in tokens:
                    matched = True
                    break
            if matched:
                mapping[canonical] = orig_col
                used_cols.add(orig_col)
                break

    return mapping


def _deduplicate_headers(raw_row) -> list[str]:
    """Takroriy yoki bo'sh ustun nomlarini unikal ko'rinishga keltiradi."""
    seen: dict[str, int] = {}
    result: list[str] = []
    for idx, c in enumerate(raw_row):
        base = str(c).strip() if c is not None and str(c).strip() else f"col_{idx}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        result.append(base if count == 1 else f"{base} ({count})")
    return result


def _get_series(df: pd.DataFrame, col_name: str, index=None) -> pd.Series:
    """Har doim Series qaytaradi (takroriy ustun bo'lsa ham DataFrame qaytarmaydi)."""
    obj = df.loc[index, col_name] if index is not None else df[col_name]
    if isinstance(obj, pd.DataFrame):
        return obj.iloc[:, 0]
    return obj


def _clean_numeric_series(series: pd.Series) -> pd.Series:
    """Vektorlashgan Decimal-xavfsiz raqamli tozalash (nuqta saqlanadi, vergul -> nuqta)."""
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    s = series.fillna("0").astype(str).str.strip()
    s = s.str.replace("\xa0", "", regex=False).str.replace(" ", "", regex=False)
    s = s.str.replace(",", ".", regex=False)
    s = s.str.replace(r"[^\d.\-]", "", regex=True)
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


_SHEET_ROLE_KEYWORDS = {
    "kirim": ("kirim", "кирим", "приход", "поступление", "inflow"),
    "chiqim": ("chiqim", "чиким", "чиқим", "расход", "продажа", "реализация", "sotuv", "outflow"),
}


def _select_worksheet(wb, role: str | None = None, sheet_name: str | None = None):
    """Ko'p varaqli Excel faylidan rolga (kirim/chiqim) yoki tanlangan nomga mos varaqni tanlaydi."""
    if sheet_name and sheet_name in wb.sheetnames:
        return wb[sheet_name]
    if role in _SHEET_ROLE_KEYWORDS:
        keywords = _SHEET_ROLE_KEYWORDS[role]
        for name in wb.sheetnames:
            low = name.strip().lower()
            if any(kw in low for kw in keywords):
                return wb[name]
    return wb.active


def _iter_file_chunks(
    file_path: Path,
    chunk_size: int = CHUNK_SIZE,
    role: str | None = None,
    sheet_name: str | None = None,
):
    """Katta Excel/CSV fayllarni xotirani to'ldirmasdan bo'laklab (streaming) o'qiydi."""
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        for chunk in pd.read_csv(file_path, chunksize=chunk_size, dtype=str, keep_default_na=False):
            yield chunk
        return

    if suffix == ".xls":
        df = pd.read_excel(file_path, sheet_name=sheet_name or 0, dtype=str, keep_default_na=False)
        for start in range(0, max(len(df), 1), chunk_size):
            yield df.iloc[start : start + chunk_size]
        return

    # .xlsx streaming via openpyxl read_only=True
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    try:
        ws = _select_worksheet(wb, role=role, sheet_name=sheet_name)
        rows_iter = ws.iter_rows(values_only=True)
        headers = None
        for row in rows_iter:
            if row and any(cell is not None and str(cell).strip() for cell in row):
                headers = _deduplicate_headers(row)
                break
        if not headers:
            return

        batch: list[tuple] = []
        for row in rows_iter:
            if not row or not any(cell is not None and str(cell).strip() for cell in row):
                continue
            batch.append(row[: len(headers)])
            if len(batch) >= chunk_size:
                yield pd.DataFrame(batch, columns=headers)
                batch.clear()
        if batch:
            yield pd.DataFrame(batch, columns=headers)
    finally:
        wb.close()


def read_file_headers(file_obj_or_path, role: str | None = None, sheet_name: str | None = None) -> list[str]:
    """Fayldan faqat birinchi bo'sh bo'lmagan sarlavha qatorini o'qiydi (zero-OOM)."""
    return read_file_preview(file_obj_or_path, max_rows=0, role=role, sheet_name=sheet_name)["headers"]


def read_file_preview(
    file_obj_or_path,
    max_rows: int = 10,
    role: str | None = None,
    sheet_name: str | None = None,
) -> dict:
    """Fayldan sarlavha, varaqlar ro'yxati va dastlabki max_rows qatorni tezkor (zero-OOM) o'qiydi."""
    name = getattr(file_obj_or_path, "name", str(file_obj_or_path))
    suffix = Path(name).suffix.lower()
    is_file_like = not isinstance(file_obj_or_path, (str, Path))
    pos = file_obj_or_path.tell() if is_file_like else 0

    try:
        if suffix == ".csv":
            df = pd.read_csv(file_obj_or_path, nrows=max_rows, dtype=str, keep_default_na=False)
            return {
                "headers": [str(c).strip() for c in df.columns],
                "rows": df.values.tolist() if max_rows > 0 else [],
                "sheets": [],
                "selected_sheet": "",
            }
        if suffix == ".xls":
            df = pd.read_excel(file_obj_or_path, sheet_name=sheet_name or 0, nrows=max_rows, dtype=str, keep_default_na=False)
            return {
                "headers": [str(c).strip() for c in df.columns],
                "rows": df.values.tolist() if max_rows > 0 else [],
                "sheets": [],
                "selected_sheet": "",
            }
        wb = openpyxl.load_workbook(file_obj_or_path, read_only=True, data_only=True)
        try:
            ws = _select_worksheet(wb, role=role, sheet_name=sheet_name)
            headers: list[str] = []
            rows: list[list[str]] = []
            for row in ws.iter_rows(values_only=True):
                if not row or not any(cell is not None and str(cell).strip() for cell in row):
                    continue
                if not headers:
                    headers = _deduplicate_headers(row)
                    if max_rows <= 0:
                        break
                    continue
                rows.append(["" if c is None else str(c).strip() for c in row[: len(headers)]])
                if len(rows) >= max_rows:
                    break
            return {
                "headers": headers,
                "rows": rows,
                "sheets": list(wb.sheetnames),
                "selected_sheet": ws.title,
            }
        finally:
            wb.close()
    finally:
        if is_file_like:
            file_obj_or_path.seek(pos)


def check_files_compatibility(
    kirim_file,
    chiqim_file,
    kirim_col_map: dict[str, str] | None = None,
    chiqim_col_map: dict[str, str] | None = None,
    kirim_sheet: str | None = None,
    chiqim_sheet: str | None = None,
) -> dict:
    """Alohida Kirim va Chiqim hujjatlarining ustunlari va kalitlari mosligini tekshiradi."""
    errors: list[str] = []
    warnings: list[str] = []

    try:
        kirim_cols = read_file_headers(kirim_file, role="kirim", sheet_name=kirim_sheet)
    except Exception as exc:
        return {"compatible": False, "errors": [f"Kirim faylini o'qishda xatolik: {exc}"], "warnings": [], "kirim_map": {}, "chiqim_map": {}}

    try:
        chiqim_cols = read_file_headers(chiqim_file, role="chiqim", sheet_name=chiqim_sheet)
    except Exception as exc:
        return {"compatible": False, "errors": [f"Chiqim faylini o'qishda xatolik: {exc}"], "warnings": [], "kirim_map": {}, "chiqim_map": {}}

    kirim_map = map_headers(kirim_cols)
    if kirim_col_map:
        kirim_map.update({k: v for k, v in kirim_col_map.items() if v})

    chiqim_map = map_headers(chiqim_cols)
    if chiqim_col_map:
        chiqim_map.update({k: v for k, v in chiqim_col_map.items() if v})

    if "tovar_nomi" not in kirim_map:
        errors.append("Kirim hujjatida tovar nomi ustuni topilmadi (masalan: 'Tovar nomi', 'Наименование').")
    if "kirim_soni" not in kirim_map and "quantity" not in kirim_map and "bosh_qoldiq_soni" not in kirim_map:
        errors.append("Kirim hujjatida miqdor ustuni topilmadi (masalan: 'Kirim', 'Soni', 'Miqdor', 'Приход', 'Количество').")

    if "tovar_nomi" not in chiqim_map:
        errors.append("Chiqim hujjatida tovar nomi ustuni topilmadi (masalan: 'Tovar nomi', 'Наименование').")
    if "chiqim_soni" not in chiqim_map and "quantity" not in chiqim_map:
        errors.append("Chiqim hujjatida miqdor ustuni topilmadi (masalan: 'Chiqim', 'Soni', 'Miqdor', 'Расход', 'Количество').")

    if ("tovar_id" in kirim_map) != ("tovar_id" in chiqim_map):
        warnings.append("Bir hujjatda Tovar ID/MXIK ustuni bor, ikkinchisida yo'q — tovarlar Kirill nomi bo'yicha moslashtiriladi.")
    if (
        "ortacha_narx" not in kirim_map
        and "ortacha_narx" not in chiqim_map
        and "summa" not in kirim_map
        and "summa" not in chiqim_map
    ):
        warnings.append("Ikkala hujjatda ham narx yoki summa ustuni topilmadi — summalar 0.00 ko'rinishida hisoblanadi.")

    return {
        "compatible": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "kirim_map": kirim_map,
        "chiqim_map": chiqim_map,
    }


def _read_chunks_into_acc(
    path: Path,
    mode: str,
    agg_chunks: list[pd.DataFrame],
    marking_acc: dict[str, dict],
    progress_callback: Callable[[int], None] | None = None,
    progress_base: int = 15,
    explicit_map: dict[str, str] | None = None,
    sheet_name: str | None = None,
) -> bool:
    """
    Faylni oqimli o'qib, agg_chunks va marking_acc ga yig'adi.
    mode: 'combined' | 'kirim' | 'chiqim'
    """
    has_marking_cols = False
    header_map: dict[str, str] | None = None
    role = mode if mode in ("kirim", "chiqim") else None

    for chunk_idx, raw_df in enumerate(_iter_file_chunks(path, role=role, sheet_name=sheet_name)):
        if raw_df.empty:
            continue
        if header_map is None:
            header_map = map_headers(list(raw_df.columns))
            if explicit_map:
                header_map.update({k: v for k, v in explicit_map.items() if v and v in raw_df.columns})
            if "tovar_nomi" not in header_map:
                raise ValueError(
                    f"{path.name}: tovar nomi ustuni topilmadi (masalan: 'Tovar nomi', 'Наименование')."
                )
            has_marking_cols = any(
                k in header_map for k in ("bosh_markirovka", "kirim_markirovka", "chiqim_markirovka", "markirovka")
            )

        df = pd.DataFrame(index=raw_df.index)
        if "tovar_id" in header_map:
            df["tovar_id"] = (
                _get_series(raw_df, header_map["tovar_id"])
                .fillna("")
                .astype(str)
                .str.strip()
                .str.replace(r"\.0+$", "", regex=True)
            )
        else:
            df["tovar_id"] = ""
        df["tovar_nomi_raw"] = _get_series(raw_df, header_map["tovar_nomi"]).fillna("").astype(str).str.strip()
        df = df[df["tovar_nomi_raw"] != ""].copy()
        if df.empty:
            continue

        df["birligi"] = (
            _get_series(raw_df, header_map["birligi"], df.index).fillna("dona").astype(str).str.strip()
            if "birligi" in header_map
            else "dona"
        )
        df.loc[df["birligi"] == "", "birligi"] = "dona"

        if mode == "kirim":
            df["bosh_qoldiq_soni"] = (
                _clean_numeric_series(raw_df.loc[df.index, header_map["bosh_qoldiq_soni"]])
                if "bosh_qoldiq_soni" in header_map else 0.0
            )
            k_col = header_map.get("kirim_soni") or header_map.get("quantity")
            df["kirim_soni"] = _clean_numeric_series(raw_df.loc[df.index, k_col]) if k_col else 0.0
            df["chiqim_soni"] = 0.0
        elif mode == "chiqim":
            df["bosh_qoldiq_soni"] = 0.0
            df["kirim_soni"] = 0.0
            c_col = header_map.get("chiqim_soni") or header_map.get("quantity")
            df["chiqim_soni"] = _clean_numeric_series(raw_df.loc[df.index, c_col]) if c_col else 0.0
        else:
            for num_col in ("bosh_qoldiq_soni", "kirim_soni", "chiqim_soni"):
                df[num_col] = (
                    _clean_numeric_series(raw_df.loc[df.index, header_map[num_col]])
                    if num_col in header_map else 0.0
                )

        if mode == "kirim":
            qty_for_price = np.where(df["kirim_soni"] > 0, df["kirim_soni"], df["bosh_qoldiq_soni"])
        elif mode == "chiqim":
            qty_for_price = df["chiqim_soni"]
        else:
            qty_for_price = np.where(
                df["kirim_soni"] > 0,
                df["kirim_soni"],
                np.where(df["bosh_qoldiq_soni"] > 0, df["bosh_qoldiq_soni"], df["chiqim_soni"]),
            )

        if "summa" in header_map and (
            (explicit_map and "summa" in explicit_map) or "ortacha_narx" not in header_map
        ):
            summa_s = _clean_numeric_series(raw_df.loc[df.index, header_map["summa"]])
            sum_vals = summa_s
            qty_vals = np.where(summa_s > 0, qty_for_price, 0.0)
        else:
            unit_price = (
                _clean_numeric_series(raw_df.loc[df.index, header_map["ortacha_narx"]])
                if "ortacha_narx" in header_map else pd.Series(0.0, index=df.index)
            )
            eff_qty = np.where(qty_for_price > 0, qty_for_price, 1.0)
            sum_vals = np.where(unit_price > 0, unit_price * eff_qty, 0.0)
            qty_vals = np.where(unit_price > 0, eff_qty, 0.0)

        # BHMS 4 / IAS 2: Kirim (tannarx) ustuvor, Chiqim (sotuv) narxi faqat kirim yo'q tovarlar uchun zaxira
        if mode == "chiqim":
            df["_kirim_summa_total"] = 0.0
            df["_kirim_qty_for_price"] = 0.0
            df["_chiqim_summa_total"] = sum_vals
            df["_chiqim_qty_for_price"] = qty_vals
        else:
            df["_kirim_summa_total"] = sum_vals
            df["_kirim_qty_for_price"] = qty_vals
            df["_chiqim_summa_total"] = 0.0
            df["_chiqim_qty_for_price"] = 0.0

        # Lotin -> Kirill (unikal nomlar bo'yicha keshlangan konvertatsiya — 1M qatorda juda tez)
        unique_raw_names = df["tovar_nomi_raw"].unique()
        cyr_map = {name: latin_to_cyrillic(name) for name in unique_raw_names}
        df["tovar_nomi_kirill"] = df["tovar_nomi_raw"].map(cyr_map)

        # Markirovka kodlarini yig'ish (agar ustunlar mavjud bo'lsa)
        if has_marking_cols:
            bosh_col = header_map.get("bosh_markirovka") if mode != "chiqim" else None
            kirim_col = (
                (header_map.get("kirim_markirovka") or header_map.get("markirovka"))
                if mode in ("combined", "kirim") else None
            )
            chiqim_col = (
                (header_map.get("chiqim_markirovka") or (header_map.get("markirovka") if mode == "chiqim" else None))
                if mode in ("combined", "chiqim") else None
            )

            for idx_row in df.index:
                tid = df.at[idx_row, "tovar_id"]
                tname = df.at[idx_row, "tovar_nomi_kirill"]
                key = tid if tid else tname
                rec = marking_acc.setdefault(
                    key,
                    {
                        "tovar_id": tid,
                        "tovar_nomi_kirill": tname,
                        "bosh": [],
                        "kirim": [],
                        "chiqim": [],
                    },
                )
                if bosh_col:
                    rec["bosh"].extend(parse_marking_codes(raw_df.at[idx_row, bosh_col]))
                if kirim_col:
                    rec["kirim"].extend(parse_marking_codes(raw_df.at[idx_row, kirim_col]))
                if chiqim_col:
                    rec["chiqim"].extend(parse_marking_codes(raw_df.at[idx_row, chiqim_col]))

        # Chunk ichida birlamchi guruhlash (vaznli o'rtacha narx uchun summa va miqdorni jamlaymiz)
        df["group_key"] = np.where(df["tovar_id"] != "", df["tovar_id"], df["tovar_nomi_kirill"])
        grouped = df.groupby("group_key", as_index=False).agg(
            tovar_id=("tovar_id", "first"),
            tovar_nomi_kirill=("tovar_nomi_kirill", "first"),
            birligi=("birligi", "first"),
            bosh_qoldiq_soni=("bosh_qoldiq_soni", "sum"),
            kirim_soni=("kirim_soni", "sum"),
            chiqim_soni=("chiqim_soni", "sum"),
            _kirim_summa_total=("_kirim_summa_total", "sum"),
            _kirim_qty_for_price=("_kirim_qty_for_price", "sum"),
            _chiqim_summa_total=("_chiqim_summa_total", "sum"),
            _chiqim_qty_for_price=("_chiqim_qty_for_price", "sum"),
        )
        agg_chunks.append(grouped)

        if progress_callback and chunk_idx % 2 == 0:
            progress_callback(min(55, progress_base + chunk_idx * 5))

    return has_marking_cols


def _finalize_svod_and_marking(
    agg_chunks: list[pd.DataFrame],
    marking_acc: dict[str, dict],
    has_marking_cols: bool,
    progress_callback: Callable[[int], None] | None = None,
) -> dict:
    if not agg_chunks:
        return {
            "items": [],
            "marking_records": [],
            "fuzzy_merged_count": 0,
            "total_shortage_amount": Decimal("0.00"),
            "marking_discrepancy_count": 0,
        }

    combined = pd.concat(agg_chunks, ignore_index=True)

    # RapidFuzz deduplikatsiya (tovar_id bo'sh bo'lgan nomlar uchun)
    fuzzy_merged_count = 0
    combined["is_fuzzy_merged"] = False
    no_id_mask = combined["tovar_id"] == ""
    if no_id_mask.any():
        unique_no_id = combined.loc[no_id_mask, "tovar_nomi_kirill"].unique().tolist()
        if len(unique_no_id) <= 10_000:
            name_map, fuzzy_merged_count = deduplicate_names(unique_no_id, threshold=92)
            mapped_names = combined.loc[no_id_mask, "tovar_nomi_kirill"].map(name_map)
            combined.loc[no_id_mask, "is_fuzzy_merged"] = (
                mapped_names != combined.loc[no_id_mask, "tovar_nomi_kirill"]
            )
            combined.loc[no_id_mask, "tovar_nomi_kirill"] = mapped_names
            combined.loc[no_id_mask, "group_key"] = mapped_names

    # Yakuniy Svod guruhlash (BHMS 4: Kirim tannarxi ustuvor, Chiqim narxi faqat kirim bo'lmaganda)
    final_df = combined.groupby("group_key", as_index=False).agg(
        tovar_id=("tovar_id", "first"),
        tovar_nomi_kirill=("tovar_nomi_kirill", "first"),
        birligi=("birligi", "first"),
        bosh_qoldiq_soni=("bosh_qoldiq_soni", "sum"),
        kirim_soni=("kirim_soni", "sum"),
        chiqim_soni=("chiqim_soni", "sum"),
        _kirim_summa_total=("_kirim_summa_total", "sum"),
        _kirim_qty_for_price=("_kirim_qty_for_price", "sum"),
        _chiqim_summa_total=("_chiqim_summa_total", "sum"),
        _chiqim_qty_for_price=("_chiqim_qty_for_price", "sum"),
        is_fuzzy_merged=("is_fuzzy_merged", "any"),
    )
    kirim_price = np.where(
        final_df["_kirim_qty_for_price"] > 0,
        final_df["_kirim_summa_total"] / final_df["_kirim_qty_for_price"],
        0.0,
    )
    chiqim_price = np.where(
        final_df["_chiqim_qty_for_price"] > 0,
        final_df["_chiqim_summa_total"] / final_df["_chiqim_qty_for_price"],
        0.0,
    )
    final_df["ortacha_narx"] = np.where(kirim_price > 0, kirim_price, chiqim_price)

    if progress_callback:
        progress_callback(65)

    # Vektorlashgan hisob-kitoblar (NumPy)
    narx = final_df["ortacha_narx"].to_numpy(dtype=np.float64)
    bosh = final_df["bosh_qoldiq_soni"].to_numpy(dtype=np.float64)
    kirim = final_df["kirim_soni"].to_numpy(dtype=np.float64)
    chiqim = final_df["chiqim_soni"].to_numpy(dtype=np.float64)

    mavjud = bosh + kirim
    farq_qoldiq_soni = np.maximum(mavjud - chiqim, 0.0)
    farq_ortiqcha_soni = np.maximum(chiqim - mavjud, 0.0)

    final_df["bosh_qoldiq_summa"] = bosh * narx
    final_df["kirim_summa"] = kirim * narx
    final_df["chiqim_summa"] = chiqim * narx
    final_df["farq_qoldiq_soni"] = farq_qoldiq_soni
    final_df["farq_qoldiq_summa"] = farq_qoldiq_soni * narx
    final_df["farq_ortiqcha_soni"] = farq_ortiqcha_soni
    final_df["farq_ortiqcha_summa"] = farq_ortiqcha_soni * narx

    items: list[dict] = []
    total_shortage_amount = Decimal("0.00")
    q2 = Decimal("0.01")
    q3 = Decimal("0.001")

    for row in final_df.itertuples(index=False):
        ortiqcha_summa = Decimal(str(round(row.farq_ortiqcha_summa, 2))).quantize(q2, rounding=ROUND_HALF_UP)
        total_shortage_amount += ortiqcha_summa
        items.append(
            {
                "tovar_id": str(row.tovar_id)[:100],
                "tovar_nomi_kirill": str(row.tovar_nomi_kirill)[:500],
                "birligi": (str(row.birligi)[:30] or "dona"),
                "ortacha_narx": Decimal(str(round(row.ortacha_narx, 2))).quantize(q2, rounding=ROUND_HALF_UP),
                "bosh_qoldiq_soni": Decimal(str(round(row.bosh_qoldiq_soni, 3))).quantize(q3, rounding=ROUND_HALF_UP),
                "bosh_qoldiq_summa": Decimal(str(round(row.bosh_qoldiq_summa, 2))).quantize(q2, rounding=ROUND_HALF_UP),
                "kirim_soni": Decimal(str(round(row.kirim_soni, 3))).quantize(q3, rounding=ROUND_HALF_UP),
                "kirim_summa": Decimal(str(round(row.kirim_summa, 2))).quantize(q2, rounding=ROUND_HALF_UP),
                "chiqim_soni": Decimal(str(round(row.chiqim_soni, 3))).quantize(q3, rounding=ROUND_HALF_UP),
                "chiqim_summa": Decimal(str(round(row.chiqim_summa, 2))).quantize(q2, rounding=ROUND_HALF_UP),
                "farq_qoldiq_soni": Decimal(str(round(row.farq_qoldiq_soni, 3))).quantize(q3, rounding=ROUND_HALF_UP),
                "farq_qoldiq_summa": Decimal(str(round(row.farq_qoldiq_summa, 2))).quantize(q2, rounding=ROUND_HALF_UP),
                "farq_ortiqcha_soni": Decimal(str(round(row.farq_ortiqcha_soni, 3))).quantize(q3, rounding=ROUND_HALF_UP),
                "farq_ortiqcha_summa": ortiqcha_summa,
                "is_fuzzy_merged": bool(row.is_fuzzy_merged),
            }
        )

    marking_records: list[dict] = []
    marking_discrepancy_count = 0
    if has_marking_cols:
        item_lookup = {(it["tovar_id"] if it["tovar_id"] else it["tovar_nomi_kirill"]): it for it in items}
        for key, m_data in marking_acc.items():
            bosh_codes = parse_marking_codes(m_data["bosh"])
            kirim_codes = parse_marking_codes(m_data["kirim"])
            chiqim_codes = parse_marking_codes(m_data["chiqim"])
            # Markirovkalanmaydigan oddiy tovarlarni (kirimda ham, chiqimda ham 0 kod) soxta kamchilikka chiqarmaymiz
            if not bosh_codes and not kirim_codes and not chiqim_codes:
                continue
            matched_item = item_lookup.get(key)
            kirim_qty = matched_item["kirim_soni"] if matched_item else Decimal("0.000")
            chiqim_qty = matched_item["chiqim_soni"] if matched_item else Decimal("0.000")
            record = audit_marking_record(
                tovar_id=str(m_data["tovar_id"])[:100],
                tovar_nomi_kirill=str(m_data["tovar_nomi_kirill"])[:500],
                bosh_codes=bosh_codes,
                kirim_tovar_soni=kirim_qty,
                kirim_codes=kirim_codes,
                chiqim_tovar_soni=chiqim_qty,
                chiqim_codes=chiqim_codes,
            )
            if record["has_discrepancy"]:
                marking_discrepancy_count += 1
            marking_records.append(record)

    if progress_callback:
        progress_callback(80)

    return {
        "items": items,
        "marking_records": marking_records,
        "fuzzy_merged_count": fuzzy_merged_count,
        "total_shortage_amount": total_shortage_amount,
        "marking_discrepancy_count": marking_discrepancy_count,
    }


def process_inventory_file(
    file_path: str | Path,
    progress_callback: Callable[[int], None] | None = None,
) -> dict:
    """Bitta umumiy faylni oqimli o'qib, Svod va Markirovka auditini bajaradi."""
    agg_chunks: list[pd.DataFrame] = []
    marking_acc: dict[str, dict] = {}
    has_marking_cols = _read_chunks_into_acc(
        Path(file_path), "combined", agg_chunks, marking_acc, progress_callback, progress_base=15
    )
    return _finalize_svod_and_marking(agg_chunks, marking_acc, has_marking_cols, progress_callback)


def process_separate_files(
    kirim_path: str | Path,
    chiqim_path: str | Path,
    progress_callback: Callable[[int], None] | None = None,
    kirim_col_map: dict[str, str] | None = None,
    chiqim_col_map: dict[str, str] | None = None,
    kirim_sheet: str | None = None,
    chiqim_sheet: str | None = None,
) -> dict:
    """Alohida Kirim va Chiqim hujjatlarini oqimli o'qib, birlashtiradi va audit qiladi."""
    agg_chunks: list[pd.DataFrame] = []
    marking_acc: dict[str, dict] = {}
    has_kirim_marking = _read_chunks_into_acc(
        Path(kirim_path),
        "kirim",
        agg_chunks,
        marking_acc,
        progress_callback,
        progress_base=15,
        explicit_map=kirim_col_map,
        sheet_name=kirim_sheet,
    )
    if progress_callback:
        progress_callback(40)
    has_chiqim_marking = _read_chunks_into_acc(
        Path(chiqim_path),
        "chiqim",
        agg_chunks,
        marking_acc,
        progress_callback,
        progress_base=40,
        explicit_map=chiqim_col_map,
        sheet_name=chiqim_sheet,
    )
    return _finalize_svod_and_marking(
        agg_chunks,
        marking_acc,
        has_kirim_marking or has_chiqim_marking,
        progress_callback,
    )
