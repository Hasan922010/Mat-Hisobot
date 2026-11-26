import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

from reports.services.ai_advisor import build_compact_metrics
from reports.services.audit_engine import (
    check_files_compatibility,
    process_inventory_file,
    process_separate_files,
    read_file_headers,
)
from reports.services.excel_builder import build_report_workbook


def run_audit(batch):
    paths = {role: f"/audit/{role}.{extension}" for role, extension in batch["files"].items()}
    for path in paths.values():
        if Path(path).suffix == ".xlsx":
            with ZipFile(path) as archive:
                members = archive.infolist()
                if len(members) > 5000 or sum(entry.file_size for entry in members) > 128 * 1024 * 1024:
                    return {"error": "Excel fayli ochilganda juda katta hajmga ega."}

    warnings = []
    if "combined" in paths:
        result = process_inventory_file(paths["combined"])
    else:
        options = batch["options"]
        settings = {
            f"{role}_{key}": options[role][field] or None
            for role in ("kirim", "chiqim")
            for key, field in (("sheet", "sheet"), ("col_map", "columns"))
        }
        for role in ("kirim", "chiqim"):
            headers = read_file_headers(paths[role], role=role, sheet_name=settings[f"{role}_sheet"])
            if any(column not in headers for column in options[role]["columns"].values()):
                return {"error": "Qo‘lda belgilangan ustun sarlavhalari faylda topilmadi."}
        compatibility = check_files_compatibility(paths["kirim"], paths["chiqim"], **settings)
        if not compatibility["compatible"]:
            return {"error": " ".join(compatibility["errors"])}
        warnings = compatibility["warnings"]
        result = process_separate_files(paths["kirim"], paths["chiqim"], **settings)

    items = result["items"]
    marking = result["marking_records"]
    if not items:
        return {"error": "Faylda tahlil qilish uchun tovar qatorlari topilmadi."}

    with open("/audit/export.xlsx", "w+b") as output:
        build_report_workbook(batch["company"], batch["stir"], batch["year"], items, marking, batch["period"], output_file=output)

    metrics = build_compact_metrics(SimpleNamespace(
        company=SimpleNamespace(name=batch["company"], stir=batch["stir"]),
        year=batch["year"], period_label=batch["period"], total_shortage_amount=result["total_shortage_amount"],
        marking_discrepancy_count=result["marking_discrepancy_count"],
    ), items, marking)
    summary = {
        "items": len(items),
        "shortages": sum(item["farq_ortiqcha_soni"] > 0 for item in items),
        "marking": len(marking),
        "discrepancies": result["marking_discrepancy_count"],
        "fuzzyMerged": result["fuzzy_merged_count"],
        "shortageValue": str(result["total_shortage_amount"]),
        "endingValue": str(sum((item["farq_qoldiq_summa"] for item in items), Decimal("0.00"))),
        "turnover": metrics["aylanma_koeffitsiyenti"],
        "inventoryDays": metrics["dio_kun"],
        "warnings": warnings,
    }
    return {"summary": summary, "items": items, "marking": marking}


def audit_json(batch_json):
    try:
        result = run_audit(json.loads(batch_json))
    except ValueError as error:
        if "tovar nomi ustuni topilmadi" in str(error):
            return json.dumps({"error": "Tovar nomi ustuni topilmadi. Jadval sarlavhalarini tekshiring."})
        raise
    return json.dumps(result, default=str, allow_nan=False)
