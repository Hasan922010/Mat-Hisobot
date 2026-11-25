"""Web, HTMX jonli progress va Excel eksport ko'rinishlari."""

from __future__ import annotations

from decimal import Decimal
import json
import tempfile

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django_q.tasks import async_task

from .models import Company, ReportBatch
from .services.audit_engine import check_files_compatibility, map_headers, read_file_preview
from .services.excel_builder import build_report_workbook
from .validators import validate_uploaded_file


def _get_user_batch(request, pk: int) -> ReportBatch:
    qs = ReportBatch.objects.select_related("company")
    if request.user.is_superuser:
        return get_object_or_404(qs, pk=pk)
    return get_object_or_404(qs, pk=pk, created_by=request.user)


def _extract_col_map(post_data, prefix: str) -> dict[str, str]:
    marking_canonical = "kirim_markirovka" if prefix == "kirim" else "chiqim_markirovka"
    field_pairs = (
        ("tovar_id", f"{prefix}_col_mxik"),
        (marking_canonical, f"{prefix}_col_markirovka"),
        ("tovar_nomi", f"{prefix}_col_tovar"),
        ("quantity", f"{prefix}_col_soni"),
        ("summa", f"{prefix}_col_summa"),
    )
    return {
        canonical: post_data.get(form_key, "").strip()
        for canonical, form_key in field_pairs
        if post_data.get(form_key, "").strip()
    }


@login_required
def preview_file(request):
    if request.method != "POST":
        return HttpResponse(status=405)

    role = request.POST.get("role", "kirim")
    if role not in ("kirim", "chiqim"):
        role = "kirim"

    uploaded_file = request.FILES.get(f"{role}_file")
    requested_sheet = request.POST.get(f"{role}_sheet", "").strip() or None
    try:
        validate_uploaded_file(uploaded_file)
        preview = read_file_preview(uploaded_file, max_rows=10, role=role, sheet_name=requested_sheet)
    except ValidationError as exc:
        return render(
            request,
            "reports/partials/file_preview.html",
            {"role": role, "error": exc.message},
        )
    except Exception as exc:
        return render(
            request,
            "reports/partials/file_preview.html",
            {"role": role, "error": f"Faylni o'qishda xatolik: {exc}"},
        )

    headers = preview["headers"]
    detected = map_headers(headers)
    soni_default = (
        detected.get("kirim_soni" if role == "kirim" else "chiqim_soni")
        or detected.get("quantity", "")
    )
    markirovka_default = (
        detected.get("kirim_markirovka" if role == "kirim" else "chiqim_markirovka")
        or detected.get("markirovka", "")
    )
    auto_map = {
        "mxik": detected.get("tovar_id", ""),
        "markirovka": markirovka_default,
        "tovar": detected.get("tovar_nomi", ""),
        "soni": soni_default,
        "summa": detected.get("summa", ""),
    }

    return render(
        request,
        "reports/partials/file_preview.html",
        {
            "role": role,
            "role_label": "Kirim hujjati" if role == "kirim" else "Chiqim hujjati",
            "filename": uploaded_file.name,
            "headers": headers,
            "rows": preview["rows"],
            "sheets": preview.get("sheets", []),
            "selected_sheet": preview.get("selected_sheet", ""),
            "preview_script_id": f"preview-payload-{role}",
            "preview_payload": {
                "headers": headers,
                "rows": preview["rows"],
                "auto": auto_map,
            },
        },
    )


@login_required
def check_compatibility(request):
    if request.method != "POST":
        return HttpResponse(status=405)

    kirim_file = request.FILES.get("kirim_file")
    chiqim_file = request.FILES.get("chiqim_file")
    errors: list[str] = []

    for label, f in (("Kirim hujjati", kirim_file), ("Chiqim hujjati", chiqim_file)):
        try:
            validate_uploaded_file(f)
        except ValidationError as exc:
            errors.append(f"{label}: {exc.message}")

    if errors:
        return render(
            request,
            "reports/partials/compatibility_result.html",
            {"result": {"compatible": False, "errors": errors, "warnings": []}},
        )

    kirim_col_map = _extract_col_map(request.POST, "kirim")
    chiqim_col_map = _extract_col_map(request.POST, "chiqim")
    kirim_sheet = request.POST.get("kirim_sheet", "").strip() or None
    chiqim_sheet = request.POST.get("chiqim_sheet", "").strip() or None
    result = check_files_compatibility(
        kirim_file,
        chiqim_file,
        kirim_col_map=kirim_col_map,
        chiqim_col_map=chiqim_col_map,
        kirim_sheet=kirim_sheet,
        chiqim_sheet=chiqim_sheet,
    )
    return render(request, "reports/partials/compatibility_result.html", {"result": result})


@login_required
def dashboard(request):
    if request.method == "POST":
        company_name = request.POST.get("company_name", "").strip()
        stir = request.POST.get("stir", "").strip()
        year_raw = request.POST.get("year", "").strip()
        period_label = request.POST.get("period_label", "Yillik").strip() or "Yillik"

        kirim_file = request.FILES.get("kirim_file")
        chiqim_file = request.FILES.get("chiqim_file")
        legacy_file = request.FILES.get("file")

        if not company_name or not stir or not year_raw.isdigit():
            messages.error(request, "Korxona nomi, STIR va yilni to'g'ri kiriting.")
            return redirect("reports:dashboard")

        if legacy_file and not (kirim_file or chiqim_file):
            try:
                validate_uploaded_file(legacy_file)
            except ValidationError as exc:
                messages.error(request, exc.message)
                return redirect("reports:dashboard")
            kirim_col_map = {}
            chiqim_col_map = {}
            kirim_sheet = None
            chiqim_sheet = None
        else:
            if not kirim_file or not chiqim_file:
                messages.error(request, "Alohida Kirim va Chiqim hujjatlarining ikkalasini ham tanlang.")
                return redirect("reports:dashboard")
            try:
                validate_uploaded_file(kirim_file)
                validate_uploaded_file(chiqim_file)
            except ValidationError as exc:
                messages.error(request, exc.message)
                return redirect("reports:dashboard")

            kirim_col_map = _extract_col_map(request.POST, "kirim")
            chiqim_col_map = _extract_col_map(request.POST, "chiqim")
            kirim_sheet = request.POST.get("kirim_sheet", "").strip() or None
            chiqim_sheet = request.POST.get("chiqim_sheet", "").strip() or None
            compat = check_files_compatibility(
                kirim_file,
                chiqim_file,
                kirim_col_map=kirim_col_map,
                chiqim_col_map=chiqim_col_map,
                kirim_sheet=kirim_sheet,
                chiqim_sheet=chiqim_sheet,
            )
            if not compat["compatible"]:
                for err in compat["errors"]:
                    messages.error(request, err)
                return redirect("reports:dashboard")

        company, created = Company.objects.get_or_create(
            stir=stir,
            defaults={"name": company_name},
        )
        if not created and company.name != company_name:
            company.name = company_name
            company.save(update_fields=["name"])

        batch = ReportBatch.objects.create(
            company=company,
            created_by=request.user,
            year=int(year_raw),
            period_label=period_label,
            uploaded_file=legacy_file,
            kirim_file=kirim_file,
            chiqim_file=chiqim_file,
            column_config={
                "kirim": kirim_col_map,
                "chiqim": chiqim_col_map,
                "kirim_sheet": kirim_sheet,
                "chiqim_sheet": chiqim_sheet,
            },
            status="PENDING",
            progress_percent=0,
        )
        async_task("reports.tasks.process_report_batch", batch.id)
        return redirect("reports:batch_detail", pk=batch.pk)

    selected_stir = request.GET.get("stir", "").strip()
    batches_qs = ReportBatch.objects.select_related("company").all()
    if not request.user.is_superuser:
        batches_qs = batches_qs.filter(created_by=request.user)
    if selected_stir:
        batches_qs = batches_qs.filter(company__stir=selected_stir)

    companies = Company.objects.all()[:50]
    batches = batches_qs[:50]

    # Davrlararo solishtirish: bir xil korxonaning yakunlangan hisobotlari
    comparison_batches = []
    if selected_stir:
        comparison_batches = list(
            ReportBatch.objects.filter(company__stir=selected_stir, status="COMPLETED")
            .order_by("year", "created_at")
        )

    return render(
        request,
        "reports/dashboard.html",
        {
            "companies": companies,
            "batches": batches,
            "selected_stir": selected_stir,
            "comparison_batches": comparison_batches,
        },
    )


@login_required
def batch_detail(request, pk: int):
    batch = _get_user_batch(request, pk)
    search_q = request.GET.get("q", "").strip()
    tab = request.GET.get("tab", "svod")

    items_qs = batch.items.all().order_by("id")
    if search_q:
        items_qs = items_qs.filter(
            Q(tovar_nomi_kirill__icontains=search_q) | Q(tovar_id__icontains=search_q)
        )

    shortage_qs = items_qs.filter(farq_ortiqcha_soni__gt=0)
    marking_qs = batch.marking_records.all().order_by("id")
    discrepancy_qs = marking_qs.filter(has_discrepancy=True)

    if search_q:
        marking_qs = marking_qs.filter(
            Q(tovar_nomi_kirill__icontains=search_q) | Q(tovar_id__icontains=search_q)
        )
        discrepancy_qs = discrepancy_qs.filter(
            Q(tovar_nomi_kirill__icontains=search_q) | Q(tovar_id__icontains=search_q)
        )

    items_page = Paginator(items_qs, 50).get_page(request.GET.get("page"))
    shortage_page = Paginator(shortage_qs, 50).get_page(request.GET.get("s_page"))
    marking_page = Paginator(marking_qs, 50).get_page(request.GET.get("m_page"))
    discrepancy_page = Paginator(discrepancy_qs, 50).get_page(request.GET.get("d_page"))
    total_ending_asset = batch.items.aggregate(s=Sum("farq_qoldiq_summa"))["s"] or Decimal("0.00")

    return render(
        request,
        "reports/detail.html",
        {
            "batch": batch,
            "tab": tab,
            "search_q": search_q,
            "items_page": items_page,
            "shortage_page": shortage_page,
            "marking_page": marking_page,
            "discrepancy_page": discrepancy_page,
            "shortage_count": shortage_qs.count(),
            "marking_count": marking_qs.count(),
            "total_ending_asset": total_ending_asset,
        },
    )


@login_required
def batch_progress(request, pk: int):
    batch = _get_user_batch(request, pk)
    response = render(request, "reports/partials/progress.html", {"batch": batch})
    if batch.status in ("COMPLETED", "FAILED"):
        response["HX-Refresh"] = "true"
    return response


@login_required
def export_excel(request, pk: int):
    batch = _get_user_batch(request, pk)
    items = batch.items.all().order_by("id").iterator(chunk_size=5000)
    marking_records = batch.marking_records.all().order_by("id").iterator(chunk_size=5000)

    spooled = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024)
    build_report_workbook(
        company_name=batch.company.name,
        company_stir=batch.company.stir,
        year=batch.year,
        items=items,
        marking_records=marking_records,
        period_label=batch.period_label,
        output_file=spooled,
    )
    filename = f"MatHisobot_{batch.company.stir}_{batch.year}_{batch.pk}.xlsx"
    return FileResponse(
        spooled,
        as_attachment=True,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@login_required
@require_POST
def delete_batch(request, pk: int):
    batch = _get_user_batch(request, pk)
    label = f"{batch.company.name} ({batch.year})"
    batch.delete()
    messages.info(request, f"{label} hisoboti o'chirildi.")
    return redirect("reports:dashboard")
