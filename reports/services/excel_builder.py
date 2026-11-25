"""Rasmiy Moddiy Hisobot, MXIK Jamlama va Markirovka Excel (.xlsx) eksport generatori."""

from __future__ import annotations

from collections import OrderedDict
from io import BytesIO
from typing import Iterable

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

_THIN_SIDE = Side(border_style="thin", color="CBD5E1")
_BORDER_THIN = Border(left=_THIN_SIDE, right=_THIN_SIDE, top=_THIN_SIDE, bottom=_THIN_SIDE)

_FONT_MAIN_TITLE = Font(name="Calibri", size=14, bold=True, color="1F2937")
_FONT_SUBTITLE = Font(name="Calibri", size=10, italic=True, color="4B5563")
_FONT_HEADER = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
_FONT_BOLD = Font(name="Calibri", size=10, bold=True, color="0F172A")
_FONT_REGULAR = Font(name="Calibri", size=10, color="1E293B")

_FILL_EMERALD = PatternFill(start_color="065F46", end_color="065F46", fill_type="solid")
_FILL_EMERALD_SUB = PatternFill(start_color="047857", end_color="047857", fill_type="solid")
_FILL_HEADER_BLUE = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
_FILL_SUBHEADER = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
_FILL_TOTAL = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
_FILL_WARNING = PatternFill(start_color="FFEBEB", end_color="FFEBEB", fill_type="solid")

_ALIGN_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
_ALIGN_LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
_ALIGN_RIGHT = Alignment(horizontal="right", vertical="center")

_FMT_MONEY = "#,##0.00"
_FMT_QTY = "#,##0.###"


def _get(obj, key: str, default=0):
    return getattr(obj, key, default) if hasattr(obj, key) else obj.get(key, default)


def _safe_cell_text(val) -> str:
    """Excel Formula Injection (CWE-1236) himoyasi: =,+,-,@ bilan boshlanuvchi matnni zararsizlantiradi."""
    text = "" if val is None else str(val)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def _join_codes(codes: list[str] | None) -> str:
    if not codes:
        return ""
    joined = ", ".join(str(c) for c in codes)
    joined = joined[:32700] + "..." if len(joined) > 32700 else joined
    return _safe_cell_text(joined)


def _style_header_rows(ws, rows: tuple[int, ...], max_col: int, fill_top, fill_sub) -> None:
    for r in rows:
        ws.row_dimensions[r].height = 22
        for c in range(1, max_col + 1):
            cell = ws.cell(row=r, column=c)
            cell.font = _FONT_HEADER
            cell.fill = fill_top if r == rows[0] else fill_sub
            cell.alignment = _ALIGN_CENTER
            cell.border = _BORDER_THIN


def build_report_workbook(
    company_name: str,
    company_stir: str,
    year: int,
    items: Iterable,
    marking_records: Iterable,
    period_label: str = "Yillik",
    output_file=None,
):
    """
    Shablonga mos ko'p varaqli .xlsx hisobot yaratadi:
      1. Moddiy_Hisobot (11 ustun, emerald sarlavha)
      2. MXIK_Jamlama (13 ustun, MXIK bo'yicha jamlama)
      3. Kirimsiz_Sotuv_Tahlili (Kirimsiz sotuvlar tahlili)
      4. Markirovka_Materiallar
      5. Markirovka_Kamchiliklari
    """
    wb = openpyxl.Workbook()

    # =========================================================================
    # 1-VARAQ: Moddiy_Hisobot (Shablon asosida)
    # =========================================================================
    ws_mh = wb.active
    ws_mh.title = "Moddiy_Hisobot"

    ws_mh["A1"] = f"Moddiy Hisobot - {company_name}"
    ws_mh["A1"].font = _FONT_MAIN_TITLE
    ws_mh["A2"] = f"Davr: {year} ({period_label}) | STIR: {company_stir}"
    ws_mh["A2"].font = _FONT_SUBTITLE

    ws_mh.merge_cells("A4:A5")
    ws_mh["A4"] = "Mahsulot nomi"
    ws_mh.merge_cells("B4:B5")
    ws_mh["B4"] = "Birlik"
    ws_mh.merge_cells("C4:D4")
    ws_mh["C4"] = "Boshlang'ich qoldiq"
    ws_mh["C5"], ws_mh["D5"] = "Miqdor", "Summa"
    ws_mh.merge_cells("E4:F4")
    ws_mh["E4"] = "Kirim"
    ws_mh["E5"], ws_mh["F5"] = "Miqdor", "Summa"
    ws_mh.merge_cells("G4:H4")
    ws_mh["G4"] = "Chiqim"
    ws_mh["G5"], ws_mh["H5"] = "Miqdor", "Summa"
    ws_mh.merge_cells("I4:I5")
    ws_mh["I4"] = "O'rtacha narx"
    ws_mh.merge_cells("J4:K4")
    ws_mh["J4"] = "Oxirgi qoldiq"
    ws_mh["J5"], ws_mh["K5"] = "Miqdor", "Summa"

    _style_header_rows(ws_mh, (4, 5), 11, _FILL_EMERALD, _FILL_EMERALD_SUB)

    mxik_groups: OrderedDict[str, dict] = OrderedDict()
    shortage_items: list[dict] = []
    r_mh = 6
    for item in items:
        mxik = str(_get(item, "tovar_id", "") or "").strip() or "-"
        name = str(_get(item, "tovar_nomi_kirill", ""))
        birlik = str(_get(item, "birligi", "dona") or "dona")
        bosh_q = float(_get(item, "bosh_qoldiq_soni", 0))
        kirim_q = float(_get(item, "kirim_soni", 0))
        chiqim_q = float(_get(item, "chiqim_soni", 0))
        narx = float(_get(item, "ortacha_narx", 0))

        if chiqim_q > (bosh_q + kirim_q):
            shortage_items.append(
                {
                    "tovar_id": "" if mxik == "-" else mxik,
                    "tovar_nomi_kirill": name,
                    "bosh_qoldiq_soni": bosh_q,
                    "kirim_soni": kirim_q,
                    "chiqim_soni": chiqim_q,
                    "ortacha_narx": narx,
                }
            )

        row_vals = [
            _safe_cell_text(name),
            _safe_cell_text(birlik),
            bosh_q,
            f"=C{r_mh}*I{r_mh}",
            kirim_q,
            f"=E{r_mh}*I{r_mh}",
            chiqim_q,
            f"=G{r_mh}*I{r_mh}",
            narx,
            f"=C{r_mh}+E{r_mh}-G{r_mh}",
            f"=J{r_mh}*I{r_mh}",
        ]
        for c_idx, val in enumerate(row_vals, start=1):
            c = ws_mh.cell(row=r_mh, column=c_idx, value=val)
            c.font = _FONT_REGULAR
            c.border = _BORDER_THIN
            if c_idx <= 2:
                c.alignment = _ALIGN_LEFT if c_idx == 1 else _ALIGN_CENTER
            else:
                c.alignment = _ALIGN_RIGHT
                c.number_format = _FMT_MONEY if c_idx in (4, 6, 8, 9, 11) else _FMT_QTY

        # MXIK_Jamlama uchun agregatsiya
        grp = mxik_groups.setdefault(
            mxik,
            {
                "mxik": mxik,
                "sample_name": name,
                "birlik": birlik,
                "types_count": 0,
                "bosh_q": 0.0,
                "bosh_s": 0.0,
                "kirim_q": 0.0,
                "kirim_s": 0.0,
                "chiqim_q": 0.0,
                "chiqim_s": 0.0,
            },
        )
        grp["types_count"] += 1
        grp["bosh_q"] += bosh_q
        grp["bosh_s"] += bosh_q * narx
        grp["kirim_q"] += kirim_q
        grp["kirim_s"] += kirim_q * narx
        grp["chiqim_q"] += chiqim_q
        grp["chiqim_s"] += chiqim_q * narx

        r_mh += 1

    last_mh = r_mh - 1
    ws_mh.cell(row=r_mh, column=1, value="JAMI").alignment = _ALIGN_LEFT
    for c_idx in (4, 6, 8, 11):
        col_l = get_column_letter(c_idx)
        c = ws_mh.cell(
            row=r_mh,
            column=c_idx,
            value=f"=SUM({col_l}6:{col_l}{last_mh})" if last_mh >= 6 else 0,
        )
        c.alignment = _ALIGN_RIGHT
        c.number_format = _FMT_MONEY
    for c_idx in range(1, 12):
        c = ws_mh.cell(row=r_mh, column=c_idx)
        c.font = _FONT_BOLD
        c.fill = _FILL_TOTAL
        c.border = _BORDER_THIN

    # Netting Risk himoyasi: Musbat ombor aktivi va manfiy (kirimsiz sotuv) tafovutini alohida ajratish
    if last_mh >= 6:
        for offset, (label, formula, fill) in enumerate(
            (
                ("Jami haqiqiy ombor qoldig'i (Aktiv):", f'=SUMIF(K6:K{last_mh}, ">0")', _FILL_TOTAL),
                ("Jami kirimsiz sotuv (Manfiy tafovut):", f'=ABS(SUMIF(K6:K{last_mh}, "<0"))', _FILL_WARNING),
            ),
            start=1,
        ):
            rec_row = r_mh + offset
            ws_mh.merge_cells(f"A{rec_row}:J{rec_row}")
            ws_mh[f"A{rec_row}"] = label
            ws_mh[f"A{rec_row}"].alignment = _ALIGN_RIGHT
            val_cell = ws_mh.cell(row=rec_row, column=11, value=formula)
            val_cell.alignment = _ALIGN_RIGHT
            val_cell.number_format = _FMT_MONEY
            for c_idx in range(1, 12):
                cell = ws_mh.cell(row=rec_row, column=c_idx)
                cell.font = _FONT_BOLD
                cell.fill = fill
                cell.border = _BORDER_THIN

    for idx, w in enumerate([52, 12, 14, 18, 14, 18, 14, 18, 16, 14, 18], start=1):
        ws_mh.column_dimensions[get_column_letter(idx)].width = w

    # =========================================================================
    # 2-VARAQ: MXIK_Jamlama (Shablon asosida)
    # =========================================================================
    ws_mx = wb.create_sheet("MXIK_Jamlama")
    ws_mx["A1"] = f"MXIK (IKPU) bo'yicha Tovar va Moddiy Qoldiqlar Jamlamasi - {company_name}"
    ws_mx["A1"].font = _FONT_MAIN_TITLE
    ws_mx["A2"] = f"Davr: {year} ({period_label}) | STIR: {company_stir}"
    ws_mx["A2"].font = _FONT_SUBTITLE

    for col_ref, title in (
        ("A4:A5", "№"),
        ("B4:B5", "MXIK (IKPU) Kodi"),
        ("C4:C5", "Mahsulotlar toifasi / Namunasi"),
        ("D4:D5", "Birligi"),
        ("E4:E5", "Tovarlar turlari soni"),
    ):
        ws_mx.merge_cells(col_ref)
        ws_mx[col_ref.split(":")[0]] = title

    for col_ref, title, c1, c2 in (
        ("F4:G4", "Boshlang'ich qoldiq", "F5", "G5"),
        ("H4:I4", "Davr kirimi", "H5", "I5"),
        ("J4:K4", "Davr chiqimi", "J5", "K5"),
        ("L4:M4", "Yakuniy qoldiq", "L5", "M5"),
    ):
        ws_mx.merge_cells(col_ref)
        ws_mx[col_ref.split(":")[0]] = title
        ws_mx[c1] = "Tovarlar soni"
        ws_mx[c2] = "Summasi (so'm)"

    _style_header_rows(ws_mx, (4, 5), 13, _FILL_EMERALD, _FILL_EMERALD_SUB)

    r_mx = 6
    for idx_num, grp in enumerate(mxik_groups.values(), start=1):
        vals = [
            idx_num,
            _safe_cell_text(grp["mxik"]),
            _safe_cell_text(grp["sample_name"]),
            _safe_cell_text(grp["birlik"]),
            grp["types_count"],
            grp["bosh_q"],
            round(grp["bosh_s"], 2),
            grp["kirim_q"],
            round(grp["kirim_s"], 2),
            grp["chiqim_q"],
            round(grp["chiqim_s"], 2),
            f"=F{r_mx}+H{r_mx}-J{r_mx}",
            f"=G{r_mx}+I{r_mx}-K{r_mx}",
        ]
        for c_idx, val in enumerate(vals, start=1):
            c = ws_mx.cell(row=r_mx, column=c_idx, value=val)
            c.font = _FONT_REGULAR
            c.border = _BORDER_THIN
            if c_idx in (1, 4):
                c.alignment = _ALIGN_CENTER
            elif c_idx in (2, 3):
                c.alignment = _ALIGN_LEFT
            else:
                c.alignment = _ALIGN_RIGHT
                c.number_format = _FMT_MONEY if c_idx in (7, 9, 11, 13) else _FMT_QTY
        r_mx += 1

    last_mx = r_mx - 1
    ws_mx.merge_cells(f"A{r_mx}:D{r_mx}")
    ws_mx[f"A{r_mx}"] = "JAMI:"
    ws_mx[f"A{r_mx}"].alignment = _ALIGN_LEFT
    for c_idx in range(5, 14):
        col_l = get_column_letter(c_idx)
        c = ws_mx.cell(
            row=r_mx,
            column=c_idx,
            value=f"=SUM({col_l}6:{col_l}{last_mx})" if last_mx >= 6 else 0,
        )
        c.alignment = _ALIGN_RIGHT
        c.number_format = _FMT_MONEY if c_idx in (7, 9, 11, 13) else _FMT_QTY
    for c_idx in range(1, 14):
        c = ws_mx.cell(row=r_mx, column=c_idx)
        c.font = _FONT_BOLD
        c.fill = _FILL_TOTAL
        c.border = _BORDER_THIN

    for idx, w in enumerate([6, 22, 38, 10, 18, 16, 20, 16, 20, 16, 20, 16, 22], start=1):
        ws_mx.column_dimensions[get_column_letter(idx)].width = w

    # =========================================================================
    # 3-VARAQ: Kirimsiz_Sotuv_Tahlili
    # =========================================================================
    ws1 = wb.create_sheet("Kirimsiz_Sotuv_Tahlili")
    ws1.merge_cells("A1:M1")
    ws1["A1"] = (
        f'"{company_name}" (STIR: {company_stir}) MCHJ tomonidan '
        f"{year} yil davomida Kirimsiz sotilgan tovarlar taxlili"
    )
    ws1["A1"].font = _FONT_MAIN_TITLE
    ws1["A1"].alignment = _ALIGN_CENTER
    ws1.row_dimensions[1].height = 28

    ws1.merge_cells("A2:A3")
    ws1["A2"] = "MXIK"
    ws1.merge_cells("B2:B3")
    ws1["B2"] = "Tovar Nomi"
    ws1.merge_cells("C2:D2")
    ws1["C2"] = f"{year} yil 1-yanvar"
    ws1["C3"], ws1["D3"] = "Soni", "Qoldiq"
    ws1.merge_cells("E2:H2")
    ws1["E2"] = f"{year}"
    ws1["E3"], ws1["F3"], ws1["G3"], ws1["H3"] = "Soni", "Kirim", "Soni", "Chiqim"
    ws1.merge_cells("I2:I3")
    ws1["I2"] = "O'rtacha bir donasini narxi"
    ws1.merge_cells("J2:M2")
    ws1["J2"] = "Farqi"
    ws1["J3"], ws1["K3"], ws1["L3"], ws1["M3"] = "Soni", "Qoldiq", "Soni", "Ortiqcha"

    _style_header_rows(ws1, (2, 3), 13, _FILL_HEADER_BLUE, _FILL_SUBHEADER)

    row_num = 4
    for item in shortage_items:
        mxik = item["tovar_id"]
        name = item["tovar_nomi_kirill"]
        bosh = item["bosh_qoldiq_soni"]
        kirim = item["kirim_soni"]
        chiqim = item["chiqim_soni"]
        narx = item["ortacha_narx"]

        row_values = [
            _safe_cell_text(mxik),
            _safe_cell_text(name),
            bosh,
            f"=C{row_num}*I{row_num}",
            kirim,
            f"=E{row_num}*I{row_num}",
            chiqim,
            f"=G{row_num}*I{row_num}",
            narx,
            f"=MAX(C{row_num}+E{row_num}-G{row_num}, 0)",
            f"=J{row_num}*I{row_num}",
            f"=MAX(G{row_num}-(C{row_num}+E{row_num}), 0)",
            f"=L{row_num}*I{row_num}",
        ]
        for col_idx, val in enumerate(row_values, start=1):
            c = ws1.cell(row=row_num, column=col_idx, value=val)
            c.font = _FONT_REGULAR
            c.border = _BORDER_THIN
            if col_idx in (1, 2):
                c.alignment = _ALIGN_LEFT
            else:
                c.alignment = _ALIGN_RIGHT
                c.number_format = _FMT_MONEY if col_idx in (4, 6, 8, 9, 11, 13) else _FMT_QTY
        row_num += 1

    last_data_row = row_num - 1
    jami_row = row_num
    ws1.cell(row=jami_row, column=1, value="").alignment = _ALIGN_LEFT
    ws1.cell(row=jami_row, column=2, value="JAMI").alignment = _ALIGN_LEFT
    for col_idx in range(3, 14):
        col_letter = get_column_letter(col_idx)
        formula = f"=SUM({col_letter}4:{col_letter}{last_data_row})" if last_data_row >= 4 else 0
        c = ws1.cell(row=jami_row, column=col_idx, value=formula)
        c.alignment = _ALIGN_RIGHT
        c.number_format = _FMT_MONEY if col_idx in (4, 6, 8, 9, 11, 13) else _FMT_QTY

    for col_idx in range(1, 14):
        c = ws1.cell(row=jami_row, column=col_idx)
        c.font = _FONT_BOLD
        c.fill = _FILL_TOTAL
        c.border = _BORDER_THIN

    for idx, w in enumerate([20, 42, 12, 16, 12, 16, 12, 16, 18, 12, 16, 12, 16], start=1):
        ws1.column_dimensions[get_column_letter(idx)].width = w

    # =========================================================================
    # 4-VARAQ: Markirovka_Materiallar
    # =========================================================================
    ws2 = wb.create_sheet("Markirovka_Materiallar")
    headers_2 = [
        "MXIK / Tovar ID",
        "Tovar Nomi",
        "Yil boshi markirovka soni",
        "Yil boshi markirovka kodlari",
        "Kirim tovar soni",
        "Kirim markirovka soni",
        "Kirim markirovka kodlari",
        "Chiqim tovar soni",
        "Chiqim markirovka soni",
        "Chiqim markirovka kodlari",
        "Qoldiq markirovka soni",
        "Omborda qolgan markirovka kodlari",
    ]
    ws2.append(headers_2)
    _style_header_rows(ws2, (1,), len(headers_2), _FILL_HEADER_BLUE, _FILL_HEADER_BLUE)

    discrepancy_rows = []
    for r_idx, rec in enumerate(marking_records, start=2):
        if _get(rec, "has_discrepancy", False):
            discrepancy_rows.append(rec)

        vals = [
            _get(rec, "tovar_id", ""),
            _get(rec, "tovar_nomi_kirill", ""),
            int(_get(rec, "bosh_markirovka_soni", 0)),
            _join_codes(_get(rec, "bosh_markirovkalar", [])),
            float(_get(rec, "kirim_tovar_soni", 0)),
            int(_get(rec, "kirim_markirovka_soni", 0)),
            _join_codes(_get(rec, "kirim_markirovkalar", [])),
            float(_get(rec, "chiqim_tovar_soni", 0)),
            int(_get(rec, "chiqim_markirovka_soni", 0)),
            _join_codes(_get(rec, "chiqim_markirovkalar", [])),
            int(_get(rec, "qoldiq_markirovka_soni", 0)),
            _join_codes(_get(rec, "qoldiq_markirovkalar", [])),
        ]
        for col_idx, val in enumerate(vals, start=1):
            c = ws2.cell(row=r_idx, column=col_idx, value=val)
            c.font = _FONT_REGULAR
            c.border = _BORDER_THIN
            c.alignment = _ALIGN_RIGHT if col_idx in (3, 5, 6, 8, 9, 11) else _ALIGN_LEFT

    for idx in range(1, len(headers_2) + 1):
        ws2.column_dimensions[get_column_letter(idx)].width = 24 if idx in (2, 4, 7, 10, 12) else 16

    # =========================================================================
    # 5-VARAQ: Markirovka_Kamchiliklari
    # =========================================================================
    ws3 = wb.create_sheet("Markirovka_Kamchiliklari")
    headers_3 = [
        "MXIK / Tovar ID",
        "Tovar Nomi",
        "Kirim tovar soni",
        "Kirim markirovka soni",
        "Kirim farqi",
        "Chiqim tovar soni",
        "Chiqim markirovka soni",
        "Chiqim farqi",
        "Noma'lum sotilgan markirovkalar",
        "Kamchilik sababi",
    ]
    ws3.append(headers_3)
    _style_header_rows(ws3, (1,), len(headers_3), _FILL_HEADER_BLUE, _FILL_HEADER_BLUE)

    for r_idx, rec in enumerate(discrepancy_rows, start=2):
        vals = [
            _get(rec, "tovar_id", ""),
            _get(rec, "tovar_nomi_kirill", ""),
            float(_get(rec, "kirim_tovar_soni", 0)),
            int(_get(rec, "kirim_markirovka_soni", 0)),
            float(_get(rec, "kirim_farqi", 0)),
            float(_get(rec, "chiqim_tovar_soni", 0)),
            int(_get(rec, "chiqim_markirovka_soni", 0)),
            float(_get(rec, "chiqim_farqi", 0)),
            _join_codes(_get(rec, "noma_lum_chiqim_markirovkalar", [])),
            _get(rec, "kamchilik_sababi", ""),
        ]
        for col_idx, val in enumerate(vals, start=1):
            c = ws3.cell(row=r_idx, column=col_idx, value=val)
            c.font = _FONT_REGULAR
            c.fill = _FILL_WARNING
            c.border = _BORDER_THIN
            c.alignment = _ALIGN_RIGHT if col_idx in (3, 4, 5, 6, 7, 8) else _ALIGN_LEFT

    for idx in range(1, len(headers_3) + 1):
        ws3.column_dimensions[get_column_letter(idx)].width = 36 if idx in (2, 9, 10) else 16

    output = output_file if output_file is not None else BytesIO()
    wb.save(output)
    output.seek(0)
    return output
