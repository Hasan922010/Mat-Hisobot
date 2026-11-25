from decimal import Decimal
import time

import pandas as pd
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from reports.models import Company, MaterialLineItem, ReportBatch
from reports.tasks import process_report_batch


@pytest.fixture
def auth_client(client, django_user_model):
    user = django_user_model.objects.create_user(username="auditor", password="secret")
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_unauthenticated_access_redirects_to_login(client):
    resp = client.get(reverse("reports:dashboard"))
    assert resp.status_code == 302
    assert "/accounts/login/" in resp["Location"]


@pytest.mark.django_db
def test_end_to_end_upload_task_detail_and_excel_export(auth_client, settings, tmp_path):
    client = auth_client
    settings.MEDIA_ROOT = tmp_path
    csv_bytes = (
        "tovar_id,tovar_nomi,bosh_qoldiq,kirim,chiqim,narx,bosh_markirovka,kirim_markirovka,chiqim_markirovka\n"
        "T1,Shakar oq,5,5,12,10000.50,M1,M2;M3,M1;M2;GHOST1\n"
        "T2,Choy ko'k,10,0,4,25000.00,,,\n"
    ).encode("utf-8")

    upload = SimpleUploadedFile("test_data.csv", csv_bytes, content_type="text/csv")
    resp = client.post(
        reverse("reports:dashboard"),
        {
            "company_name": "Test Savdo MCHJ",
            "stir": "300111222",
            "year": "2026",
            "period_label": "Yillik",
            "file": upload,
        },
    )
    assert resp.status_code == 302
    batch = ReportBatch.objects.get()
    assert batch.status == "PENDING"

    # Fon vazifasini to'g'ridan-to'g'ri ishga tushiramiz
    process_report_batch(batch.id)
    batch.refresh_from_db()

    assert batch.status == "COMPLETED"
    assert batch.progress_percent == 100
    assert batch.total_items_count == 2
    assert batch.total_shortage_amount == Decimal("20001.00")
    assert batch.marking_discrepancy_count == 1  # Faqat markirovkali T1 (T2 oddiy tovar — 0 kod)
    assert "Iqtisodiy Audit Xulosasi" in batch.ai_summary_markdown
    assert "DIO" in batch.ai_summary_markdown
    assert "QQS (12%)" in batch.ai_summary_markdown

    detail_resp = client.get(reverse("reports:batch_detail", args=[batch.pk]))
    assert detail_resp.status_code == 200
    assert "Шакар оқ" in detail_resp.content.decode("utf-8")

    progress_resp = client.get(reverse("reports:batch_progress", args=[batch.pk]))
    assert progress_resp.status_code == 200
    assert progress_resp["HX-Refresh"] == "true"

    export_resp = client.get(reverse("reports:export_excel", args=[batch.pk]))
    assert export_resp.status_code == 200
    assert export_resp["Content-Disposition"].endswith('.xlsx"')


@pytest.mark.django_db
def test_100k_rows_synthetic_load_performance(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    n_rows = 100_000
    csv_path = tmp_path / "load_100k.csv"

    df = pd.DataFrame({
        "tovar_id": [f"SKU-{i % 2000}" for i in range(n_rows)],
        "tovar_nomi": [f"Mahsulot {i % 2000}" for i in range(n_rows)],
        "bosh_qoldiq": [1] * n_rows,
        "kirim": [2] * n_rows,
        "chiqim": [4] * n_rows,
        "narx": ["1500.25"] * n_rows,
    })
    df.to_csv(csv_path, index=False)

    company = Company.objects.create(name="Mega Load MCHJ", stir="999888777")
    batch = ReportBatch.objects.create(
        company=company,
        year=2026,
        period_label="Yillik",
        uploaded_file=str(csv_path),
    )
    # FileField path ni vaqtinchalik CSV ga yo'naltiramiz
    batch.uploaded_file.name = str(csv_path)
    batch.save(update_fields=["uploaded_file"])

    t0 = time.perf_counter()
    process_report_batch(batch.id)
    elapsed = time.perf_counter() - t0

    batch.refresh_from_db()
    assert batch.status == "COMPLETED"
    assert batch.total_items_count == 2000
    assert MaterialLineItem.objects.filter(batch=batch).count() == 2000
    assert elapsed < 30.0


@pytest.mark.django_db
def test_separate_kirim_chiqim_compatibility_and_import(auth_client, settings, tmp_path):
    client = auth_client
    settings.MEDIA_ROOT = tmp_path

    kirim_ok = SimpleUploadedFile(
        "kirim.csv",
        b"tovar_id,tovar_nomi,bosh_qoldiq,miqdor,narx,kirim_markirovka\nK1,Shakar oq,2,8,10000.50,M1;M2\n",
        content_type="text/csv",
    )
    chiqim_bad = SimpleUploadedFile(
        "chiqim_bad.csv",
        b"foo,bar\n1,2\n",
        content_type="text/csv",
    )

    # Moslik tekshiruvi xato qaytarishi kerak
    compat_bad = client.post(
        reverse("reports:check_compatibility"),
        {"kirim_file": kirim_ok, "chiqim_file": chiqim_bad},
    )
    assert compat_bad.status_code == 200
    assert "Moslikda xatoliklar aniqlandi" in compat_bad.content.decode("utf-8")

    # Mos kelmaydigan fayllar import qilinmasligi kerak
    kirim_ok.seek(0)
    chiqim_bad.seek(0)
    post_bad = client.post(
        reverse("reports:dashboard"),
        {
            "company_name": "Alohida Test MCHJ",
            "stir": "444555666",
            "year": "2026",
            "period_label": "Yillik",
            "kirim_file": kirim_ok,
            "chiqim_file": chiqim_bad,
        },
    )
    assert post_bad.status_code == 302
    assert ReportBatch.objects.count() == 0

    # Endi mos keluvchi Kirim va Chiqim fayllari bilan tekshiramiz
    kirim_ok.seek(0)
    chiqim_ok = SimpleUploadedFile(
        "chiqim.csv",
        b"tovar_id,tovar_nomi,miqdor,chiqim_markirovka\nK1,Shakar oq,12,M1;GHOST\n",
        content_type="text/csv",
    )
    compat_ok = client.post(
        reverse("reports:check_compatibility"),
        {"kirim_file": kirim_ok, "chiqim_file": chiqim_ok},
    )
    assert compat_ok.status_code == 200
    assert "Hujjatlar mos keldi" in compat_ok.content.decode("utf-8")

    kirim_ok.seek(0)
    chiqim_ok.seek(0)
    post_ok = client.post(
        reverse("reports:dashboard"),
        {
            "company_name": "Alohida Test MCHJ",
            "stir": "444555666",
            "year": "2026",
            "period_label": "Yillik",
            "kirim_file": kirim_ok,
            "chiqim_file": chiqim_ok,
        },
    )
    assert post_ok.status_code == 302
    batch = ReportBatch.objects.get()
    process_report_batch(batch.id)
    batch.refresh_from_db()

    assert batch.status == "COMPLETED"
    assert batch.total_items_count == 1
    item = batch.items.get()
    assert item.bosh_qoldiq_soni == Decimal("2.000")
    assert item.kirim_soni == Decimal("8.000")
    assert item.chiqim_soni == Decimal("12.000")
    assert item.farq_ortiqcha_soni == Decimal("2.000")
    assert item.farq_ortiqcha_summa == Decimal("20001.00")
    assert batch.marking_discrepancy_count == 1


@pytest.mark.django_db
def test_preview_file_and_explicit_column_mapping_summa_divided_by_soni(auth_client, settings, tmp_path):
    client = auth_client
    settings.MEDIA_ROOT = tmp_path

    # Real-time preview tekshiruvi: faqat MXIK, Markirovka, Tovar, Soni, Summa + Narxi ustunlari ko'rinishi kerak
    kirim_csv = SimpleUploadedFile(
        "kirim_custom.csv",
        b"col_code,col_mark,col_name,col_qty,col_total,extra_ignored_col\n10701001,DM1;DM2,Un oliy nav,10,150000.00,secret_extra\n",
        content_type="text/csv",
    )
    chiqim_csv = SimpleUploadedFile(
        "chiqim_custom.csv",
        b"col_code,col_mark,col_name,col_qty,col_total,extra_ignored_col\n10701001,DM1;GHOST9,Un oliy nav,14,210000.00,secret_extra\n",
        content_type="text/csv",
    )

    prev_resp = client.post(
        reverse("reports:preview_file"),
        {"role": "kirim", "kirim_file": kirim_csv},
    )
    assert prev_resp.status_code == 200
    prev_html = prev_resp.content.decode("utf-8")
    assert "Un oliy nav" in prev_html
    assert "Markirovka" in prev_html
    assert "Narxi (Summa/Soni)" in prev_html
    assert ">extra_ignored_col</th>" not in prev_html

    # Foydalanuvchi tanlagan ustunlar (jumladan Markirovka) bilan import
    kirim_csv.seek(0)
    post_resp = client.post(
        reverse("reports:dashboard"),
        {
            "company_name": "Narx Test MCHJ",
            "stir": "777888999",
            "year": "2026",
            "period_label": "Yillik",
            "kirim_file": kirim_csv,
            "chiqim_file": chiqim_csv,
            "kirim_col_mxik": "col_code",
            "kirim_col_markirovka": "col_mark",
            "kirim_col_tovar": "col_name",
            "kirim_col_soni": "col_qty",
            "kirim_col_summa": "col_total",
            "chiqim_col_mxik": "col_code",
            "chiqim_col_markirovka": "col_mark",
            "chiqim_col_tovar": "col_name",
            "chiqim_col_soni": "col_qty",
            "chiqim_col_summa": "col_total",
        },
    )
    assert post_resp.status_code == 302
    batch = ReportBatch.objects.get()
    process_report_batch(batch.id)
    batch.refresh_from_db()

    item = batch.items.get()
    assert item.tovar_id == "10701001"
    assert item.ortacha_narx == Decimal("15000.00")  # 150000 / 10 = 15000
    assert item.farq_ortiqcha_soni == Decimal("4.000")
    assert item.farq_ortiqcha_summa == Decimal("60000.00")
    assert batch.marking_discrepancy_count == 1


@pytest.mark.django_db
def test_mxik_grouping_and_preview_with_apostrophes(auth_client, settings, tmp_path):
    client = auth_client
    settings.MEDIA_ROOT = tmp_path

    kirim_csv = SimpleUploadedFile(
        "kirim_mxik.csv",
        b"MXIK,Tovar,Soni,Summa\n10701001.0,Shakar o'ram,10,120000\n",
        content_type="text/csv",
    )
    chiqim_csv = SimpleUploadedFile(
        "chiqim_mxik.csv",
        b"MXIK,\"Tovar (o'zbekcha)\",Soni,Summa\n10701001,Shakar (o'ram 1kg),15,180000\n",
        content_type="text/csv",
    )

    prev_resp = client.post(
        reverse("reports:preview_file"),
        {"role": "chiqim", "chiqim_file": chiqim_csv},
    )
    assert prev_resp.status_code == 200
    assert 'id="preview-payload-chiqim"' in prev_resp.content.decode("utf-8")

    chiqim_csv.seek(0)
    post_resp = client.post(
        reverse("reports:dashboard"),
        {
            "company_name": "MXIK MCHJ",
            "stir": "555666777",
            "year": "2026",
            "period_label": "Yillik",
            "kirim_file": kirim_csv,
            "chiqim_file": chiqim_csv,
            "chiqim_col_mxik": "MXIK",
            "chiqim_col_tovar": "Tovar (o'zbekcha)",
            "chiqim_col_soni": "Soni",
            "chiqim_col_summa": "Summa",
        },
    )
    assert post_resp.status_code == 302
    batch = ReportBatch.objects.get()
    process_report_batch(batch.id)
    batch.refresh_from_db()

    # Kirim va Chiqim nomi turlicha bo'lsa ham MXIK ("10701001") bo'yicha 1 ta qatorga birlashishi kerak
    assert batch.total_items_count == 1
    item = batch.items.get()
    assert item.tovar_id == "10701001"
    assert item.kirim_soni == Decimal("10.000")
    assert item.chiqim_soni == Decimal("15.000")
    assert item.farq_ortiqcha_soni == Decimal("5.000")


@pytest.mark.django_db
def test_security_xss_script_breakout_and_idor_blocked(auth_client, client, django_user_model, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path

    # 1. XSS </script> injeksiyasi preview_file da zararsizlantirilishi kerak
    xss_csv = SimpleUploadedFile(
        "xss.csv",
        b"MXIK,Tovar,Soni\n1,</script><script>alert(1)</script>,5\n",
        content_type="text/csv",
    )
    prev_resp = auth_client.post(reverse("reports:preview_file"), {"role": "kirim", "kirim_file": xss_csv})
    assert prev_resp.status_code == 200
    body = prev_resp.content.decode("utf-8")
    assert "</script><script>alert(1)</script>" not in body

    # 2. IDOR: boshqa foydalanuvchi birovning hisobotini ko'ra olmasligi kerak
    other_user = django_user_model.objects.create_user(username="other", password="secret")
    comp = Company.objects.create(name="Private MCHJ", stir="111222333")
    batch = ReportBatch.objects.create(company=comp, created_by=other_user, year=2026)

    assert auth_client.get(reverse("reports:batch_detail", args=[batch.pk])).status_code == 404
    assert auth_client.get(reverse("reports:export_excel", args=[batch.pk])).status_code == 404
    assert auth_client.post(reverse("reports:delete_batch", args=[batch.pk])).status_code == 404


@pytest.mark.django_db
def test_fractional_mavjud_and_delete_batch(auth_client, django_user_model):
    user = django_user_model.objects.get(username="auditor")
    comp = Company.objects.create(name="Kasr MCHJ", stir="222333444")
    batch = ReportBatch.objects.create(company=comp, created_by=user, year=2026, status="COMPLETED")
    MaterialLineItem.objects.create(
        batch=batch,
        tovar_id="M1",
        tovar_nomi_kirill="Шоколад",
        ortacha_narx=Decimal("100.00"),
        bosh_qoldiq_soni=Decimal("10.500"),
        bosh_qoldiq_summa=Decimal("1050.00"),
        kirim_soni=Decimal("2.250"),
        kirim_summa=Decimal("225.00"),
        chiqim_soni=Decimal("15.000"),
        chiqim_summa=Decimal("1500.00"),
        farq_qoldiq_soni=Decimal("0.000"),
        farq_qoldiq_summa=Decimal("0.00"),
        farq_ortiqcha_soni=Decimal("2.250"),
        farq_ortiqcha_summa=Decimal("225.00"),
    )

    detail_resp = auth_client.get(reverse("reports:batch_detail", args=[batch.pk]))
    assert detail_resp.status_code == 200
    body = detail_resp.content.decode("utf-8")
    assert "12,750" in body or "12.750" in body
    assert 'role="tab"' in body and 'role="tabpanel"' in body
    assert "cdn.tailwindcss.com" not in body and "unpkg.com" not in body

    # GET o'chirishga ruxsat bermasligi, POST esa o'chirishi kerak
    del_url = reverse("reports:delete_batch", args=[batch.pk])
    assert auth_client.get(del_url).status_code == 405
    assert auth_client.post(del_url).status_code == 302
    assert not ReportBatch.objects.filter(pk=batch.pk).exists()


@pytest.mark.django_db
def test_failed_batch_records_error_status_and_ai_fallback(monkeypatch, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    bad_csv = tmp_path / "broken.csv"
    bad_csv.write_text("foo,bar\n1,2\n", encoding="utf-8")

    comp = Company.objects.create(name="Xato MCHJ", stir="666777888")
    batch = ReportBatch.objects.create(company=comp, year=2026, uploaded_file=str(bad_csv))
    batch.uploaded_file.name = str(bad_csv)
    batch.save(update_fields=["uploaded_file"])

    with pytest.raises(ValueError):
        process_report_batch(batch.id)
    batch.refresh_from_db()
    assert batch.status == "FAILED"
    assert "tovar nomi" in batch.error_message

    # AI API xato berganda deterministik CFO xulosasiga tushishi kerak
    from reports.services import ai_advisor
    import google.genai as genai_mod

    settings.GEMINI_API_KEY = "fake-test-key"

    def _boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(genai_mod, "Client", _boom)
    summary = ai_advisor.generate_ai_summary(batch, [], [])
    assert "Iqtisodiy Audit Xulosasi" in summary
    assert "DIO" in summary
