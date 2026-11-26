from decimal import Decimal
import openpyxl

from reports.services.excel_builder import build_report_workbook


def test_build_report_workbook_three_sheets_and_formulas():
    items = [
        {
            "tovar_id": "101",
            "tovar_nomi_kirill": "Шакар оқ",
            "bosh_qoldiq_soni": Decimal("10.000"),
            "kirim_soni": Decimal("5.000"),
            "chiqim_soni": Decimal("20.000"),
            "ortacha_narx": Decimal("12000.50"),
        }
    ]
    marking_records = [
        {
            "tovar_id": "101",
            "tovar_nomi_kirill": "Шакар оқ",
            "bosh_markirovka_soni": 1,
            "bosh_markirovkalar": ["M1"],
            "kirim_tovar_soni": Decimal("5.000"),
            "kirim_markirovka_soni": 4,
            "kirim_markirovkalar": ["M2", "M3", "M4", "M5"],
            "chiqim_tovar_soni": Decimal("20.000"),
            "chiqim_markirovka_soni": 2,
            "chiqim_markirovkalar": ["M1", "GHOST"],
            "qoldiq_markirovka_soni": 4,
            "qoldiq_markirovkalar": ["M2", "M3", "M4", "M5"],
            "has_discrepancy": True,
            "kirim_farqi": Decimal("-1"),
            "chiqim_farqi": Decimal("-18"),
            "noma_lum_chiqim_markirovkalar": ["GHOST"],
            "kamchilik_sababi": "Kirim tafovuti; Ghost Marking",
        }
    ]

    stream = build_report_workbook("Baraka Savdo", "123456789", 2026, items, marking_records)
    wb = openpyxl.load_workbook(stream, data_only=False)

    assert wb.sheetnames == [
        "Moddiy_Hisobot",
        "MXIK_Jamlama",
        "Kirimsiz_Sotuv_Tahlili",
        "Markirovka_Materiallar",
        "Markirovka_Kamchiliklari",
    ]

    ws_mh = wb["Moddiy_Hisobot"]
    assert ws_mh["A1"].value == "Moddiy Hisobot - Baraka Savdo"
    assert ws_mh["A4"].value == "Mahsulot nomi"
    assert ws_mh["A6"].value == "Шакар оқ"
    assert ws_mh["D6"].value == "=C6*I6"
    assert ws_mh["J6"].value == "=C6+E6-G6"
    assert ws_mh["A7"].value == "JAMI"
    assert ws_mh["K8"].value == '=SUMIF(K6:K6, ">0")'
    assert ws_mh["K9"].value == '=ABS(SUMIF(K6:K6, "<0"))'

    ws_mx = wb["MXIK_Jamlama"]
    assert ws_mx["B4"].value == "MXIK (IKPU) Kodi"
    assert ws_mx["B6"].value == "101"
    assert ws_mx["L6"].value == "=F6+H6-J6"
    assert ws_mx["A7"].value == "JAMI:"

    ws1 = wb["Kirimsiz_Sotuv_Tahlili"]
    assert '"Baraka Savdo" (STIR: 123456789) MCHJ tomonidan 2026 yil davomida Kirimsiz sotilgan tovarlar taxlili' == ws1["A1"].value
    assert ws1["A2"].value == "MXIK"
    assert ws1["A4"].value == "101"
    assert ws1["D4"].value == "=C4*I4"
    assert ws1["J4"].value == "=MAX(C4+E4-G4, 0)"
    assert ws1["L4"].value == "=MAX(G4-(C4+E4), 0)"
    assert ws1["B5"].value == "JAMI"
    assert ws1["M5"].value == "=SUM(M4:M4)"
    assert ws1["I4"].number_format == "#,##0.00"

    ws3 = wb["Markirovka_Kamchiliklari"]
    assert ws3["A2"].value == "101"
    assert ws3["I2"].value == "GHOST"
    assert ws3["A2"].fill.start_color.rgb.endswith("FFEBEB")


def test_excel_formula_injection_is_neutralized():
    items = [
        {
            "tovar_id": "=1+1",
            "tovar_nomi_kirill": "=CMD|'/C calc'!A0",
            "bosh_qoldiq_soni": Decimal("0"),
            "kirim_soni": Decimal("1"),
            "chiqim_soni": Decimal("2"),
            "ortacha_narx": Decimal("100"),
        }
    ]
    marking = [
        {
            "tovar_id": "=1+1",
            "tovar_nomi_kirill": "+SUM(A1:A2)",
            "bosh_markirovka_soni": 0,
            "bosh_markirovkalar": [],
            "kirim_tovar_soni": Decimal("1"),
            "kirim_markirovka_soni": 0,
            "kirim_markirovkalar": [],
            "chiqim_tovar_soni": Decimal("2"),
            "chiqim_markirovka_soni": 1,
            "chiqim_markirovkalar": ["=GHOST"],
            "qoldiq_markirovka_soni": 0,
            "qoldiq_markirovkalar": [],
            "has_discrepancy": True,
            "kirim_farqi": Decimal("-1"),
            "chiqim_farqi": Decimal("-1"),
            "noma_lum_chiqim_markirovkalar": ["=GHOST"],
            "kamchilik_sababi": "@cmd",
        }
    ]
    stream = build_report_workbook("Test", "123", 2026, items, marking)
    wb = openpyxl.load_workbook(stream, data_only=False)
    assert wb["Moddiy_Hisobot"]["A6"].value == "'=CMD|'/C calc'!A0"
    assert wb["Kirimsiz_Sotuv_Tahlili"]["A4"].value == "'=1+1"
    assert wb["Kirimsiz_Sotuv_Tahlili"]["B4"].value == "'=CMD|'/C calc'!A0"
    assert wb["Markirovka_Materiallar"]["A2"].value == "'=1+1"
    assert wb["Markirovka_Materiallar"]["B2"].value == "'+SUM(A1:A2)"
    assert wb["Markirovka_Kamchiliklari"]["A2"].value == "'=1+1"
    assert wb["Markirovka_Kamchiliklari"]["B2"].value == "'+SUM(A1:A2)"
    assert wb["Markirovka_Kamchiliklari"]["J2"].value == "'@cmd"
