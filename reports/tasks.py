"""Django-Q2 asinxron fon vazifalari."""

from __future__ import annotations

import logging

from django.db import transaction

from reports.models import MarkingAuditRecord, MaterialLineItem, ReportBatch
from reports.services.ai_advisor import generate_ai_summary
from reports.services.audit_engine import process_inventory_file, process_separate_files

logger = logging.getLogger(__name__)


def process_report_batch(batch_id: int) -> None:
    """Yuklangan Excel/CSV faylni fonda qayta ishlaydi va PostgreSQL ga atomik saqlaydi."""
    batch = ReportBatch.objects.select_related("company").get(pk=batch_id)
    batch.status = "PROCESSING"
    batch.progress_percent = 10
    batch.error_message = ""
    batch.save(update_fields=["status", "progress_percent", "error_message"])

    def _update_progress(pct: int) -> None:
        ReportBatch.objects.filter(pk=batch_id).update(progress_percent=pct)

    try:
        if batch.kirim_file and batch.chiqim_file:
            col_cfg = batch.column_config or {}
            result = process_separate_files(
                batch.kirim_file.path,
                batch.chiqim_file.path,
                progress_callback=_update_progress,
                kirim_col_map=col_cfg.get("kirim"),
                chiqim_col_map=col_cfg.get("chiqim"),
                kirim_sheet=col_cfg.get("kirim_sheet"),
                chiqim_sheet=col_cfg.get("chiqim_sheet"),
            )
        else:
            result = process_inventory_file(
                batch.uploaded_file.path,
                progress_callback=_update_progress,
            )
        items = result["items"]
        marking_records = result["marking_records"]

        with transaction.atomic():
            MaterialLineItem.objects.filter(batch=batch).delete()
            MarkingAuditRecord.objects.filter(batch=batch).delete()

            line_objs = [
                MaterialLineItem(batch=batch, **it)
                for it in items
            ]
            if line_objs:
                MaterialLineItem.objects.bulk_create(line_objs, batch_size=5000)

            marking_objs = [
                MarkingAuditRecord(batch=batch, **rec)
                for rec in marking_records
            ]
            if marking_objs:
                MarkingAuditRecord.objects.bulk_create(marking_objs, batch_size=5000)

            batch.total_items_count = len(items)
            batch.total_shortage_amount = result["total_shortage_amount"]
            batch.marking_discrepancy_count = result["marking_discrepancy_count"]
            batch.fuzzy_merged_count = result["fuzzy_merged_count"]
            batch.progress_percent = 92
            batch.save(
                update_fields=[
                    "total_items_count",
                    "total_shortage_amount",
                    "marking_discrepancy_count",
                    "fuzzy_merged_count",
                    "progress_percent",
                ]
            )

        batch.ai_summary_markdown = generate_ai_summary(batch, items, marking_records)
        batch.status = "COMPLETED"
        batch.progress_percent = 100
        batch.save(update_fields=["ai_summary_markdown", "status", "progress_percent"])

    except Exception as exc:
        logger.exception("ReportBatch #%s qayta ishlashda xatolik", batch_id)
        safe_msg = str(exc) if isinstance(exc, ValueError) else "Hisobotni qayta ishlashda kutilmagan xatolik yuz berdi."
        ReportBatch.objects.filter(pk=batch_id).update(
            status="FAILED",
            error_message=safe_msg,
        )
        raise
