from decimal import Decimal
from types import SimpleNamespace
import openpyxl
import pandas as pd
import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from reports.services.audit_engine import (
    clean_decimal,
    map_headers,
    process_inventory_file,
    process_separate_files,
    read_file_preview,
)
from reports.services.fuzzy_matcher import deduplicate_names
from reports.services.transliterator import latin_to_cyrillic
from reports.validators import MAX_FILE_SIZE_BYTES, validate_uploaded_file


def test_decimal_guard_preserves_dot_and_converts_comma():
    assert clean_decimal("12500.50") == Decimal("12500.50")
    assert clean_decimal("12500,50") == Decimal("12500.50")
    assert clean_decimal("1 250 000.75 so'm") == Decimal("1250000.75")
    assert clean_decimal("45.5") == Decimal("45.50")
    assert clean_decimal(None) == Decimal("0.00")


def test_latin_to_cyrillic_digraphs():
    assert latin_to_cyrillic("O'zbekiston shakar choy") == "Ўзбекистон шакар чой"
    assert latin_to_cyrillic("G'isht yog'och yulduz yaxshi") == "Ғишт ёғоч юлдуз яхши"
    assert latin_to_cyrillic("Erkak tsirk") == "Эркак цирк"


def test_header_aliasing_uz_and_ru():
    uz_cols = ["Kod", "Tovar nomi", "Boshlangich qoldiq", "Kirim", "Chiqim", "Narx"]
    uz_map = map_headers(uz_cols)
    assert uz_map["tovar_id"] == "Kod"
    assert uz_map["tovar_nomi"] == "Tovar nomi"
    assert uz_map["bosh_qoldiq_soni"] == "Boshlangich qoldiq"
    assert uz_map["kirim_soni"] == "Kirim"
    assert uz_map["chiqim_soni"] == "Chiqim"
    assert uz_map["ortacha_narx"] == "Narx"

    ru_cols = ["Артикул", "Наименование", "Нач остаток", "Приход", "Расход", "Цена"]
    ru_map = map_headers(ru_cols)
    assert ru_map["tovar_id"] == "Артикул"
    assert ru_map["tovar_nomi"] == "Наименование"
    assert ru_map["bosh_qoldiq_soni"] == "Нач остаток"
    assert ru_map["kirim_soni"] == "Приход"
    assert ru_map["chiqim_soni"] == "Расход"
    assert ru_map["ortacha_narx"] == "Цена"


def test_process_inventory_file_shortage_and_no_synthetic_rows(tmp_path):
    csv_path = tmp_path / "sample.csv"
    df = pd.DataFrame([
        {
            "tovar_id": "101",
            "tovar_nomi": "Shakar oq",
            "bosh_qoldiq": "10",
            "kirim": "5",
            "chiqim": "20",  # Kirimsiz sotilgan = 5
            "narx": "12000.50",
        },
        {
            "tovar_id": "102",
            "tovar_nomi": "Yog' kungaboqar",
            "bosh_qoldiq": "10",
            "kirim": "10",
            "chiqim": "8",   # Qoldiq = 12
            "narx": "18500,25",
        },
    ])
    df.to_csv(csv_path, index=False)

    result = process_inventory_file(csv_path)
    items = {it["tovar_id"]: it for it in result["items"]}

    assert len(items) == 2
    assert all("KATEGORIYA SVODNIY" not in it["tovar_nomi_kirill"] for it in items.values())

    shakar = items["101"]
    assert shakar["tovar_nomi_kirill"] == "Шакар оқ"
    assert shakar["ortacha_narx"] == Decimal("12000.50")
    assert shakar["farq_qoldiq_soni"] == Decimal("0.000")
    assert shakar["farq_ortiqcha_soni"] == Decimal("5.000")
    assert shakar["farq_ortiqcha_summa"] == Decimal("60002.50")

    yog = items["102"]
    assert yog["tovar_nomi_kirill"] == "Ёғ кунгабоқар"
    assert yog["ortacha_narx"] == Decimal("18500.25")
    assert yog["farq_qoldiq_soni"] == Decimal("12.000")
    assert yog["farq_ortiqcha_soni"] == Decimal("0.000")
    assert result["total_shortage_amount"] == Decimal("60002.50")


def test_duplicate_xlsx_headers_do_not_crash_dataframe_str(tmp_path):
    xlsx_path = tmp_path / "dup_headers.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Tovar nomi", "Tovar nomi", "Kirim", "Chiqim", "Summa"])
    ws.append(["Un oliy", "Izoh", 10, 12, 100000])
    wb.save(xlsx_path)

    preview = read_file_preview(xlsx_path)
    assert preview["headers"] == ["Tovar nomi", "Tovar nomi (2)", "Kirim", "Chiqim", "Summa"]

    result = process_inventory_file(xlsx_path)
    assert len(result["items"]) == 1
    assert result["items"][0]["tovar_nomi_kirill"] == "Ун олий"
    assert result["items"][0]["ortacha_narx"] == Decimal("10000.00")


def test_weighted_average_price_across_multiple_rows(tmp_path):
    csv_path = tmp_path / "weighted.csv"
    df = pd.DataFrame([
        {"tovar_id": "W1", "tovar_nomi": "Mahsulot", "kirim": "100", "chiqim": "0", "narx": "10000"},
        {"tovar_id": "W1", "tovar_nomi": "Mahsulot", "kirim": "1", "chiqim": "0", "narx": "20000"},
    ])
    df.to_csv(csv_path, index=False)

    result = process_inventory_file(csv_path)
    assert len(result["items"]) == 1
    # (100 * 10000 + 1 * 20000) / 101 = 10099.0099 -> 10099.01
    assert result["items"][0]["ortacha_narx"] == Decimal("10099.01")


def test_kirim_cost_priority_over_chiqim_sales_price(tmp_path):
    kirim_path = tmp_path / "kirim.csv"
    chiqim_path = tmp_path / "chiqim.csv"

    pd.DataFrame([
        {"MXIK": "P1", "Tovar": "Shakar", "Soni": "100", "Summa": "1000000"},
    ]).to_csv(kirim_path, index=False)

    pd.DataFrame([
        {"MXIK": "P1", "Tovar": "Shakar", "Soni": "100", "Summa": "1500000"},
        {"MXIK": "P2", "Tovar": "Choy", "Soni": "10", "Summa": "150000"},
    ]).to_csv(chiqim_path, index=False)

    result = process_separate_files(kirim_path, chiqim_path)
    items = {it["tovar_id"]: it for it in result["items"]}

    # P1: Kirim tannarxi (10,000) sotuv narxidan (15,000) ustun bo'lishi kerak
    assert items["P1"]["ortacha_narx"] == Decimal("10000.00")
    # P2: Kirim yo'q (sof kirimsiz sotuv), shuning uchun Chiqim narxi (15,000) zaxira sifatida olinadi
    assert items["P2"]["ortacha_narx"] == Decimal("15000.00")
    assert items["P2"]["farq_ortiqcha_summa"] == Decimal("150000.00")


def test_short_alias_no_false_match_and_birligi_length_guard(tmp_path):
    # "Предприятие" ichida "ед" bor — birligi sifatida noto'g'ri tanlanmasligi kerak
    hdr = map_headers(["ID", "икпу", "Предприятие", "Сведения", "Наименование", "Приход", "Цена"])
    assert "birligi" not in hdr
    # Didox/Soliq fayllarida "икпу"/"MXIK" har doim hujjat "ID" ustunidan ustun bo'lishi kerak
    assert hdr["tovar_id"] == "икпу"
    assert map_headers(["ID", "MXIK", "Tovar"])["tovar_id"] == "MXIK"

    # Agar haqiqiy birligi ustuni 30 belgidan uzun bo'lsa ham DB VARCHAR(30) dan oshmasligi kerak
    csv_path = tmp_path / "long_unit.csv"
    pd.DataFrame([
        {
            "tovar_id": "X" * 120,
            "tovar_nomi": "Mahsulot",
            "birligi": "упаковка (12 штук по 0.5 литра в коробке)",
            "kirim": "5",
            "narx": "1000",
        }
    ]).to_csv(csv_path, index=False)

    res = process_inventory_file(csv_path)
    item = res["items"][0]
    assert len(item["birligi"]) <= 30
    assert len(item["tovar_id"]) <= 100


def test_multisheet_xlsx_auto_selects_kirim_sheet_even_if_chiqim_is_active(tmp_path):
    kirim_xlsx = tmp_path / "kirim_multi.xlsx"
    chiqim_xlsx = tmp_path / "chiqim_only.xlsx"

    wb_k = openpyxl.Workbook()
    ws_k = wb_k.active
    ws_k.title = "кирим"
    ws_k.append(["MXIK", "Tovar", "Soni", "Summa"])
    ws_k.append(["10701", "Shakar", 100, 1000000])
    ws_c = wb_k.create_sheet("чиким")
    ws_c.append(["MXIK", "Tovar", "Soni", "Summa"])
    ws_c.append(["10701", "Shakar", 30, 450000])
    wb_k.active = 1  # Oxirgi faol varaq "чиким" qilib saqlangan!
    wb_k.save(kirim_xlsx)

    wb_c = openpyxl.Workbook()
    ws_c2 = wb_c.active
    ws_c2.title = "чиким"
    ws_c2.append(["MXIK", "Tovar", "Soni", "Summa"])
    ws_c2.append(["10701", "Shakar", 30, 450000])
    wb_c.save(chiqim_xlsx)

    prev = read_file_preview(kirim_xlsx, role="kirim")
    assert prev["selected_sheet"] == "кирим"
    assert prev["sheets"] == ["кирим", "чиким"]

    res = process_separate_files(kirim_xlsx, chiqim_xlsx)
    item = res["items"][0]
    assert item["kirim_soni"] == Decimal("100.000")
    assert item["chiqim_soni"] == Decimal("30.000")
    assert item["farq_qoldiq_soni"] == Decimal("70.000")
    assert item["ortacha_narx"] == Decimal("10000.00")


def test_file_validator_blocks_spoofed_xlsx_empty_and_oversized():
    with pytest.raises(ValidationError):
        validate_uploaded_file(SimpleUploadedFile("bad.txt", b"hello"))
    with pytest.raises(ValidationError):
        validate_uploaded_file(SimpleUploadedFile("empty.csv", b""))
    with pytest.raises(ValidationError):
        validate_uploaded_file(SimpleUploadedFile("fake.xlsx", b"not-a-zip-header"))

    oversized = SimpleNamespace(name="huge.csv", size=MAX_FILE_SIZE_BYTES + 1, tell=lambda: 0, read=lambda n: b"a", seek=lambda p: None)
    with pytest.raises(ValidationError):
        validate_uploaded_file(oversized)


def test_fuzzy_matcher_merges_near_duplicates_and_keeps_distinct():
    mapping, merged = deduplicate_names(
        ["Шакар оқ 1кг", "Шакар  оқ 1кг", "Шакар оқ 1к", "Ёғ кунгабоқар 5л"],
        threshold=92,
    )
    assert merged >= 1
    assert mapping["Шакар  оқ 1кг"] == "Шакар оқ 1кг"
    assert mapping["Шакар оқ 1к"] == "Шакар оқ 1кг"
    assert mapping["Ёғ кунгабоқар 5л"] == "Ёғ кунгабоқар 5л"
