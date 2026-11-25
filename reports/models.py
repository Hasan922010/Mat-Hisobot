from django.conf import settings
from django.db import models


class Company(models.Model):
    name = models.CharField(max_length=255, verbose_name="Korxona nomi")
    stir = models.CharField(max_length=20, unique=True, db_index=True, verbose_name="STIR")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Korxona"
        verbose_name_plural = "Korxonalar"

    def __str__(self):
        return f"{self.name} (STIR: {self.stir})"


class ReportBatch(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Navbatda"),
        ("PROCESSING", "Qayta ishlanmoqda"),
        ("COMPLETED", "Tayyor"),
        ("FAILED", "Xatolik"),
    ]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="batches")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_batches",
    )
    year = models.IntegerField(db_index=True)
    period_label = models.CharField(max_length=50, default="Yillik")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING", db_index=True)
    progress_percent = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    uploaded_file = models.FileField(upload_to="uploads/%Y/%m/", null=True, blank=True)
    kirim_file = models.FileField(upload_to="uploads/%Y/%m/", null=True, blank=True)
    chiqim_file = models.FileField(upload_to="uploads/%Y/%m/", null=True, blank=True)
    column_config = models.JSONField(default=dict, blank=True)

    # Agregatlangan tezkor metrikalar
    total_items_count = models.IntegerField(default=0)
    total_shortage_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    marking_discrepancy_count = models.IntegerField(default=0)
    fuzzy_merged_count = models.IntegerField(default=0)
    ai_summary_markdown = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Hisobot paketi"
        verbose_name_plural = "Hisobot paketlari"

    def __str__(self):
        return f"{self.company.name} — {self.year} ({self.period_label}) [{self.status}]"


class MaterialLineItem(models.Model):
    batch = models.ForeignKey(ReportBatch, on_delete=models.CASCADE, related_name="items")
    tovar_id = models.CharField(max_length=100, db_index=True)
    tovar_nomi_kirill = models.CharField(max_length=500)
    birligi = models.CharField(max_length=30, default="dona")

    ortacha_narx = models.DecimalField(max_digits=18, decimal_places=2)       # H ustun
    bosh_qoldiq_soni = models.DecimalField(max_digits=18, decimal_places=3)   # B ustun
    bosh_qoldiq_summa = models.DecimalField(max_digits=20, decimal_places=2)  # C ustun
    kirim_soni = models.DecimalField(max_digits=18, decimal_places=3)         # D ustun
    kirim_summa = models.DecimalField(max_digits=20, decimal_places=2)        # E ustun
    chiqim_soni = models.DecimalField(max_digits=18, decimal_places=3)        # F ustun
    chiqim_summa = models.DecimalField(max_digits=20, decimal_places=2)       # G ustun

    farq_qoldiq_soni = models.DecimalField(max_digits=18, decimal_places=3)   # I ustun
    farq_qoldiq_summa = models.DecimalField(max_digits=20, decimal_places=2)  # J ustun
    farq_ortiqcha_soni = models.DecimalField(max_digits=18, decimal_places=3) # K ustun (Kirimsiz sotilgan)
    farq_ortiqcha_summa = models.DecimalField(max_digits=20, decimal_places=2)# L ustun
    is_fuzzy_merged = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["batch", "farq_ortiqcha_soni"]),
        ]
        verbose_name = "Material qatori"
        verbose_name_plural = "Material qatorlari"

    def __str__(self):
        return f"{self.tovar_nomi_kirill} ({self.tovar_id})"

    @property
    def mavjud_soni(self):
        return self.bosh_qoldiq_soni + self.kirim_soni


class MarkingAuditRecord(models.Model):
    batch = models.ForeignKey(ReportBatch, on_delete=models.CASCADE, related_name="marking_records")
    tovar_id = models.CharField(max_length=100, db_index=True)
    tovar_nomi_kirill = models.CharField(max_length=500)

    bosh_markirovka_soni = models.IntegerField(default=0)
    bosh_markirovkalar = models.JSONField(default=list)

    kirim_tovar_soni = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    kirim_markirovka_soni = models.IntegerField(default=0)
    kirim_markirovkalar = models.JSONField(default=list)

    chiqim_tovar_soni = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    chiqim_markirovka_soni = models.IntegerField(default=0)
    chiqim_markirovkalar = models.JSONField(default=list)

    qoldiq_markirovka_soni = models.IntegerField(default=0)
    qoldiq_markirovkalar = models.JSONField(default=list)

    has_discrepancy = models.BooleanField(default=False, db_index=True)
    kirim_farqi = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    chiqim_farqi = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    noma_lum_chiqim_markirovkalar = models.JSONField(default=list)
    kamchilik_sababi = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["batch", "has_discrepancy"]),
        ]
        verbose_name = "Markirovka auditi"
        verbose_name_plural = "Markirovka auditlari"

    def __str__(self):
        return f"{self.tovar_nomi_kirill} (Discrepancy: {self.has_discrepancy})"
