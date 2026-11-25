from django.contrib import admin
from .models import Company, MarkingAuditRecord, MaterialLineItem, ReportBatch


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "stir", "created_at")
    search_fields = ("name", "stir")


@admin.register(ReportBatch)
class ReportBatchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "company",
        "year",
        "period_label",
        "status",
        "progress_percent",
        "total_items_count",
        "total_shortage_amount",
        "marking_discrepancy_count",
        "created_at",
    )
    list_filter = ("status", "year")
    search_fields = ("company__name", "company__stir")
    readonly_fields = ("created_at",)


@admin.register(MaterialLineItem)
class MaterialLineItemAdmin(admin.ModelAdmin):
    list_display = (
        "batch",
        "tovar_id",
        "tovar_nomi_kirill",
        "ortacha_narx",
        "bosh_qoldiq_soni",
        "kirim_soni",
        "chiqim_soni",
        "farq_qoldiq_soni",
        "farq_ortiqcha_soni",
        "farq_ortiqcha_summa",
        "is_fuzzy_merged",
    )
    list_filter = ("is_fuzzy_merged", "batch")
    search_fields = ("tovar_id", "tovar_nomi_kirill")


@admin.register(MarkingAuditRecord)
class MarkingAuditRecordAdmin(admin.ModelAdmin):
    list_display = (
        "batch",
        "tovar_id",
        "tovar_nomi_kirill",
        "bosh_markirovka_soni",
        "kirim_markirovka_soni",
        "chiqim_markirovka_soni",
        "qoldiq_markirovka_soni",
        "has_discrepancy",
    )
    list_filter = ("has_discrepancy", "batch")
    search_fields = ("tovar_id", "tovar_nomi_kirill")
