from decimal import Decimal

from reports.services.marking_engine import audit_marking_record, parse_marking_codes


def test_parse_marking_codes_variants():
    assert parse_marking_codes("DM001, DM002; DM001\nDM003") == ["DM001", "DM002", "DM003"]
    assert parse_marking_codes('["K1", "K2", "K1"]') == ["K1", "K2"]
    assert parse_marking_codes(None) == []


def test_parse_gs1_datamatrix_preserves_internal_semicolon_and_comma():
    raw = '010478009675035021NqlIlPL;nUhcCpr%iyoB 010478011653002321rD;:KdpElGYsFWx,q5Mj'
    parsed = parse_marking_codes(raw)
    assert parsed == [
        "010478009675035021NqlIlPL;nUhcCpr%iyoB",
        "010478011653002321rD;:KdpElGYsFWx,q5Mj",
    ]


def test_audit_marking_record_clean():
    rec = audit_marking_record(
        tovar_id="A1",
        tovar_nomi_kirill="Сув 1л",
        bosh_codes=["M1", "M2"],
        kirim_tovar_soni=Decimal("2"),
        kirim_codes=["M3", "M4"],
        chiqim_tovar_soni=Decimal("3"),
        chiqim_codes=["M1", "M2", "M3"],
    )
    assert rec["has_discrepancy"] is False
    assert rec["qoldiq_markirovka_soni"] == 1
    assert rec["qoldiq_markirovkalar"] == ["M4"]
    assert rec["noma_lum_chiqim_markirovkalar"] == []


def test_audit_marking_record_discrepancies_and_ghost_marking():
    rec = audit_marking_record(
        tovar_id="A2",
        tovar_nomi_kirill="Шарбат",
        bosh_codes=["M1"],
        kirim_tovar_soni=Decimal("3"),
        kirim_codes=["M2", "M3"],  # farq: -1
        chiqim_tovar_soni=Decimal("2"),
        chiqim_codes=["M1", "GHOST99"],  # GHOST99 kirimda yo'q
    )
    assert rec["has_discrepancy"] is True
    assert rec["kirim_farqi"] == Decimal("-1")
    assert rec["chiqim_farqi"] == Decimal("0")
    assert rec["noma_lum_chiqim_markirovkalar"] == ["GHOST99"]
    assert "Kirim tafovuti" in rec["kamchilik_sababi"]
    assert "Ghost Marking" in rec["kamchilik_sababi"]
