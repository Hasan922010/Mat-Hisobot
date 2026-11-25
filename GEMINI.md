# GEMINI.md — MASTER SYSTEM INSTRUCTIONS, ARCHITECTURE & TZ
**Loyiha nomi:** Enterprise Material & Inventory Analytics Platform (TMQ, Kirimsiz Sotuvlar va Raqamli Markirovka Tahlili SaaS)
**Versiya:** 7.0 (10/10 Enterprise Production-Ready Edition)
**Agent Muhiti:** Google Antigravity / Gemini Code Assist (Autonomous Multi-Agent Workspace)

---

## 0. AGENT UCHUN QAT'IY QOIDALAR (SYSTEM DIRECTIVES)

Sen ushbu loyihani noldan oxirigacha quruvchi **Senior Full-Stack Architect, Python Data Engineer va Buxgalteriya-Soliq Tizimlari Mutaxassisi**san. Quyidagi qoidalarga 100% amal qilishing shart:

1. **Paketlar Boshqaruvi (`uv`):** Hech qachon `pip` yoki `poetry` ishlatma. Barcha kutubxonalar va virtual muhit faqat Astral **`uv`** (`uv init`, `uv add`, `uv run`) orqali boshqariladi.
2. **Texnologik Stek:** Backend uchun faqat **Django 5.x** + **Django REST Framework**, ma'lumotlar bazasi uchun **PostgreSQL 16+**, asinxron fon vazifalari uchun **Django-Q2** (PostgreSQL ORM broker sifatida, Redis talab qilinmaydi), Frontend uchun **Django Templates + Tailwind CSS + HTMX + Alpine.js** ishlatiladi.
3. **1 Million+ Qator Himoyasi (Anti-Freeze & Zero-OOM):**
   - Katta Excel fayllarni o'qishda `openpyxl(..., read_only=True)` yoki `pandas.read_csv(..., chunksize=50000)` oqimli (streaming) rejimidan foydalan.
   - Barcha matematik hisob-kitoblar Python `for` siklida emas, **Pandas / NumPy vektorlashgan amallari** orqali bajarilsin.
   - PostgreSQL bazasiga yozishda har doim `transaction.atomic()` ichida `bulk_create(..., batch_size=5000)` ishlatilsin.
   - Excel eksportida katta hajmlar uchun `openpyxl` ning optimallashgan yozish mexanizmi qo'llanilsin.
4. **Narx va Kasr Sonlar Aniqligi (`Decimal Guard`):**
   - Excel fayldagi narxlarni tozalashda hech qachon nuqtani (`.`) o'chirib tashlama! Vergulni (`,`) nuqtaga almashtir, `Decimal` tipiga o'tkaz va `2` xona aniqlikda saqla.
5. **Token Tejamkorligi (75–85% Optimizatsiya):**
   - Sun'iy intellekt (`google-genai`) ga hech qachon xom Excel qatorlari yoki minglab markirovka kodlarini yuborma. Faqat Python hisoblab tayyorlagan 350–550 tokenlik agregatlangan JSON metrikalarini uzat.
6. **Bosqichma-bosqich Qurish va Testlash:**
   - Har bir modul yozilgandan so'ng `uv run pytest` orqali unit-testlarni yoz va ishga tushir. Barcha testlar yashil (PASSED) bo'lmaguncha keyingi bosqichga o'tma.

---

## 1. LOYIHA MAQSADI VA BIZNES KONSEPSIYASI

Korxonalarning ombor, savdo va raqamli markirovkalash tizimlaridan (1C, MoySklad, POS-kassalar, Asl Belgisi / Soliq hisobotlari) olingan Excel (`.xlsx`, `.xls`) yoki `.csv` fayllari asosida:
1. **Materiallar Hisoboti (M-19 / Oborot-saldovaya vedomost):** Yil boshi qoldig'i, davr kirimi, davr chiqimi va davr oxiri qoldig'ini ham miqdorda, ham summada aniq hisoblash.
2. **Kirimsiz Sotilgan Tovarlar Tahlili:** Hujjatli kirim va boshlang'ich qoldiqdan ortiqcha sotib yuborilgan tovarlar va ularning moliyaviy summasini rasmiy soliq/buxgalteriya shablonida chiqarish.
3. **Raqamli Markirovka (Asl Belgisi / DataMatrix) Materiallar Hisoboti va Tafovutlar Nazorati:**
   - Har bir tovar bo'yicha qanday markirovka kodlari bilan kirim bo'lgani, qanday markirovka kodlari bilan chiqib ketgani va omborda qaysi markirovkalar qolganini aniqlash.
   - Tovar kirim/chiqim soni markirovka kodlari soniga teng bo'lishini tekshirish ($\text{Kirim Soni} == \text{Kirim Markirovka Soni}$ va $\text{Chiqim Soni} == \text{Chiqim Markirovka Soni}$).
   - Sonlar mos kelmagan yoki kirimda bo'lmagan markirovka sotilgan (**Ghost Marking**) barcha tovarlarni alohida **"Markirovka Kamchiliklari"** hisobotiga yig'ish.
4. **AI Iqtisodchi-Tahlilchi:** Rahbariyat uchun aylanma tezligi, harakatsiz zaxiralar (*Dead Stock*), kirimsiz sotuv xavflari va markirovka intizomi bo'yicha yozma ekspert xulosasini berish.

---

## 2. TIZIM ARXITEKTURASI VA FAYL STRUKTURASI

### 2.1. Ma'lumotlar Oqimi Arxitekturasi

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                FRONTEND (DJANGO TEMPLATES + TAILWIND + HTMX)            │
│  • Korxona (STIR, Nomi) va Davr (Yil/Oy)  • Drag & Drop Excel yuklash   │
│  • Jonli Progress Bar (HTMX Polling)      • Markirovka Qoldiq & Xatolar │
│  • Ko'p sahifali .xlsx eksport            • AI Iqtisodiy Tahlil         │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ HTTP / HTMX
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     DJANGO BACKEND (VIEWS & VALIDATORS)                 │
│  • File Validator (MIME type, Hajm <= 100MB, Ustunlar strukturasi)      │
│  • Task Dispatcher (Django-Q2 orqali fon rejimiga uzatish)              │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Async Task Queue (PostgreSQL Broker)
          ┌──────────────────────────┼──────────────────────────┐
          ▼                          ▼                          ▼
┌──────────────────────┐ ┌──────────────────────┐ ┌───────────────────────┐
│ ETL, SVOD & MARKING  │ │   POSTGRESQL 16 DB   │ │    EXCEL BUILDER      │
│ (Pandas + RapidFuzz) │ │ (Atomic Bulk Save)   │ │     (OpenPyXL)        │
│                      │ │                      │ │                       │
│ • Header Aliasing    │ │ • Company (STIR)     │ │ • 1-varaq: Kirimsiz   │
│ • Lotin -> Kirill    │ │ • ReportBatch        │ │   Sotuvlar Tahlili    │
│ • Fuzzy Deduplicate  │ │ • MaterialLineItem   │ │ • 2-varaq: Markirovka │
│ • Set Diff (Markirov)│ │ • MarkingAuditRecord │ │   Materiallar Hisoboti│
│ • Vectorized Svod    │ │ • DjangoQ ORM Queue  │ │ • 3-varaq: Markirovka │
└──────────┬───────────┘ └──────────────────────┘ │   Kamchiliklari       │
           │                                      └───────────────────────┘
           ▼ (Siqilgan JSON: ~450 token)
┌─────────────────────────────────────────────────────────────────────────┐
│               AI IQTISODIY TAHLILCHI (services/ai_advisor.py)           │
│  • Tovar aylanmasi  • Dead Stock  • Kirimsiz sotuv  • Markirovka xavfi  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2. Loyiha Kataloglari Strukturasi

```text
inventory_analytics/
├── GEMINI.md                   # Ushbu boshqaruv va TZ hujjati
├── pyproject.toml              # uv paketlar konfiguratsiyasi
├── uv.lock                     # uv lock fayli
├── .env                        # DB_NAME, DB_USER, DB_PASS, GEMINI_API_KEY, SECRET_KEY
├── .env.example                # Namuna muhit o'zgaruvchilari
├── manage.py                   # Django CLI
├── config/                     # Asosiy Django sozlamalari
│   ├── __init__.py
│   ├── settings.py             # PostgreSQL, Django-Q2, Media, Static sozlamalari
│   ├── urls.py
│   └── wsgi.py
├── reports/                    # Asosiy biznes ilova
│   ├── __init__.py
│   ├── admin.py                # Django Admin paneli (barcha jadvallar nazorati)
│   ├── models.py               # PostgreSQL modellari (Indekslangan)
│   ├── validators.py           # Yuklangan fayl validatsiyasi
│   ├── tasks.py                # Django-Q2 asinxron fon vazifalari
│   ├── views.py                # Web, HTMX status va eksport ko'rinishlari
│   ├── urls.py                 # App marshrutlari
│   ├── services/
│   │   ├── __init__.py
│   │   ├── transliterator.py   # Lotin -> Kirill fonetik konvertor
│   │   ├── fuzzy_matcher.py    # RapidFuzz orqali o'xshash nomlarni birlashtirish
│   │   ├── audit_engine.py     # Pandas Svod va hisob-kitob dvigateli
│   │   ├── marking_engine.py   # Markirovka kirim-chiqim, qoldiq va kamchiliklar dvigateli
│   │   ├── excel_builder.py    # 3 varaqli rasmiy Excel eksport
│   │   └── ai_advisor.py       # Token-tejamkor AI hisobot generatori
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_engine.py      # Formulalar, kasr narxlar va Kirill testlari
│   │   ├── test_marking.py     # Markirovka soni va kodlar mosligi testlari
│   │   └── test_excel.py       # OpenPyXL shablon va formulalar testi
│   └── templates/
│       └── reports/
│           ├── base.html
│           ├── dashboard.html  # Yuklash, korxonalar tarixi va davrlararo solishtirish
│           ├── detail.html     # Svod jadval + Markirovka + AI Tahlil ko'rinishi
│           └── partials/
│               └── progress.html # HTMX jonli progress komponenti
└── media/                      # Yuklangan xom Excel fayllar arxivi
```

---

## 3. POSTGRESQL MA'LUMOTLAR BAZASI MODELLARI (`reports/models.py`)

```python
from django.db import models

class Company(models.Model):
    name = models.CharField(max_length=255, verbose_name="Korxona nomi")
    stir = models.CharField(max_length=20, unique=True, db_index=True, verbose_name="STIR")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} (STIR: {self.stir})"


class ReportBatch(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Navbatda'),
        ('PROCESSING', 'Qayta ishlanmoqda'),
        ('COMPLETED', 'Tayyor'),
        ('FAILED', 'Xatolik'),
    ]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='batches')
    year = models.IntegerField(db_index=True)
    period_label = models.CharField(max_length=50, default='Yillik')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    progress_percent = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    uploaded_file = models.FileField(upload_to='uploads/%Y/%m/')
    
    # Agregatlangan tezkor metrikalar
    total_items_count = models.IntegerField(default=0)
    total_shortage_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    marking_discrepancy_count = models.IntegerField(default=0)
    fuzzy_merged_count = models.IntegerField(default=0)
    ai_summary_markdown = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class MaterialLineItem(models.Model):
    batch = models.ForeignKey(ReportBatch, on_delete=models.CASCADE, related_name='items')
    tovar_id = models.CharField(max_length=100, db_index=True)
    tovar_nomi_kirill = models.CharField(max_length=500)
    birligi = models.CharField(max_length=30, default='dona')
    
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


class MarkingAuditRecord(models.Model):
    batch = models.ForeignKey(ReportBatch, on_delete=models.CASCADE, related_name='marking_records')
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
```

---

## 4. HISOB-KITOB FORMULALARI VA ALGORITMLAR

### 4.1. Ustunlarni Avtomatik Tanish (Header Aliasing)
Yuklangan fayl o'zbekcha yoki ruscha bo'lishidan qat'i nazar ustunlar avtomatik moslashtiriladi:
- **ID/Kod:** `['tovar_id', 'kod', 'barkod', 'sku', 'id', 'mxik', 'ikpu', 'код', 'артикул']`
- **Nomi:** `['tovar_nomi', 'nomi', 'mahsulot', 'наименование', 'товар', 'номенклатура']`
- **Boshlang'ich qoldiq:** `['boshlangich_qoldiq', 'bosh_qoldiq', 'нач_остаток', 'начальный_остаток']`
- **Kirim:** `['kirim', 'kirim_miqdori', 'prikhod', 'приход', 'поступление']`
- **Chiqim:** `['chiqim', 'chiqim_miqdori', 'rasxod', 'sotuv', 'расход', 'продажа', 'реализация']`
- **Narx:** `['narx', 'tannarx', 'ortacha_narx', 'цена', 'себестоимость']`
- **Markirovka ustunlari:** `['bosh_markirovka', 'kirim_markirovka', 'chiqim_markirovka', 'markirovka', 'киз', 'datamatrix', 'sgtin']`

### 4.2. Lotin-Kirill Konvertatsiya va RapidFuzz Deduplikatsiya
1. Avval 2 harfli o'zbekcha birikmalar (`o'`, `g'`, `sh`, `ch`, `yo`, `yu`, `ya`, `ye`, `ts`), so'ngra 1 harfli belgilar Kirill alifbosiga o'tkaziladi.
2. **Hech qachon** birlashtirilgan sun'iy "KATEGORIYA SVODNIY" qatorlari ochilmaydi. Haqiqiy tovar nomi `tovar_nomi_kirill` ustunida, kodi esa `tovar_id` ustunida alohida saqlanadi.
3. Agar `tovar_id` bo'sh bo'lsa yoki turli yozilgan nomlar uchrasa, `rapidfuzz.process.extractOne` (chegara $\ge 92\%$) orqali bir xil tovarlar aniqlanib birlashtiriladi.

### 4.3. Rasmiy «Kirimsiz Sotilgan Tovarlar Tahlili» Formulalari ($i$-qator)
- $C_i$ (Boshlang'ich summa): `=B{i}*H{i}`
- $E_i$ (Kirim summa): `=D{i}*H{i}`
- $G_i$ (Chiqim summa): `=F{i}*H{i}`
- $I_i$ (Farqi — Qoldiq soni): `=MAX(B{i}+D{i}-F{i}, 0)`
- $J_i$ (Farqi — Qoldiq summa): `=I{i}*H{i}`
- $K_i$ (Farqi — Ortiqcha/Kirimsiz sotilgan soni): `=MAX(F{i}-(B{i}+D{i}), 0)`
- $L_i$ (Farqi — Ortiqcha/Kirimsiz sotilgan summa): `=K{i}*H{i}`
- **JAMI qatori:** Barcha $B$ dan $L$ gacha ustunlar uchun `=SUM(B4:B{last_row})` dinamik formulasi.

### 4.4. Raqamli Markirovka Hisoboti va Kamchiliklar Mantiqi (`marking_engine.py`)
1. **Qolgan markirovka kodlari:** $M_{\text{qoldiq}} = (M_{\text{bosh}} \cup M_{\text{kirim}}) \setminus M_{\text{chiqim}}$
2. **Kirim tafovuti:** $\Delta_{\text{kirim}} = |M_{\text{kirim}}| - Q_{\text{kirim}}$. Agar $\neq 0$ bo'lsa $\rightarrow$ Kamchilik!
3. **Chiqim tafovuti:** $\Delta_{\text{chiqim}} = |M_{\text{chiqim}}| - Q_{\text{chiqim}}$. Agar $\neq 0$ bo'lsa $\rightarrow$ Kamchilik!
4. **Noma'lum markirovka sotuvi (Ghost Marking):** $M_{\text{noma'lum}} = M_{\text{chiqim}} \setminus (M_{\text{bosh}} \cup M_{\text{kirim}})$. Agar bo'sh bo'lmasa $\rightarrow$ Kamchilik!

---

## 5. KO'P SAHIFALI EXCEL EKSPORT SHABLONI (`excel_builder.py`)

Eksport qilinadigan `.xlsx` fayl **3 ta ishchi varaq**dan iborat bo'ladi:
1. **`Kirimsiz_Sotuv_Tahlili`:**
   - `A1:L1` birlashtirilgan sarlavha: `"[Korxona Nomi]" (STIR: [STIR]) MCHJ tomonidan [Yil] yil davomida Kirimsiz sotilgan tovarlar taxlili`
   - 2-3 qatorlar: `A2:A3` (Tovar Nomi), `B2:C2` ([Yil] yil 1-yanvar: B3=Soni, C3=Qoldiq), `D2:G2` ([Yil]: D3=Soni, E3=Kirim, F3=Soni, G3=Chiqim), `H2:H3` (O'rtacha bir donasini narxi), `I2:L2` (Farqi: I3=Soni, J3=Qoldiq, K3=Soni, L3=Ortiqcha).
   - Barcha kataklarda to'liq `thin` chiziqlar, narx va summalarda `#,##0.00` formati.
2. **`Markirovka_Materiallar`:**
   - Tovar ID, Tovar Nomi, Yil boshi markirovka soni va kodlari, Kirim tovar soni, Kirim markirovka soni va kodlari, Chiqim tovar soni, Chiqim markirovka soni va kodlari, Qoldiq markirovka soni, Omborda qolgan markirovka kodlari.
3. **`Markirovka_Kamchiliklari`:**
   - Faqat `has_discrepancy == True` bo'lgan muammoli tovarlar yig'iladi. Kirim/chiqim soni tafovuti, noma'lum sotilgan markirovkalar va aniq kamchilik sababi qizil ogohlantiruvchi fonda (`#FFEBEB`) ko'rsatiladi.

---

## 6. QADAM-BA-QADAM QURISH REJASI (EXECUTION ROADMAP FOR AGENT)

Antigravity agenti loyihani quyidagi 5 ta ketma-ket bosqichda avtonom tarzda qurishi shart:

- **1-bosqich (Muhit va Baza):** `uv init` va `uv add` orqali barcha kutubxonalarni o'rnatish, `config/settings.py` da PostgreSQL va `Django-Q2` ni sozlash, `reports/models.py` ni yaratish va `makemigrations` + `migrate` bajarish.
- **2-bosqich (Core Engine & Markirovka):** `transliterator.py`, `fuzzy_matcher.py`, `audit_engine.py` va `marking_engine.py` modullarini yozish. `pytest` bilan kasr narxlar, Lotin-Kirill va markirovka set-operatsiyalarini testdan o'tkazish.
- **3-bosqich (3 Varaqli Excel Builder):** `excel_builder.py` ni yozish, `A1:L1` shablonini, dinamik `=SUM` formulalarini va markirovka varaqlarini yaratib, test fayl generatsiya qilish.
- **4-bosqich (Asinxron Tasks & AI Advisor):** `tasks.py` da `Django-Q2` worker vazifasini (`progress_percent` yangilanishi bilan) va `ai_advisor.py` da siqilgan JSON asosida AI tahlilchi modulini ulash.
- **5-bosqich (Frontend UI & Integratsiya):** Tailwind CSS + HTMX yordamida `dashboard.html` (korxonalar tarixi, fayl yuklash, jonli progress-bar) va `detail.html` (Svod jadval, Markirovka qoldiq/kamchiliklar tablari, Excel yuklab olish va AI hisoboti) sahifalarini yakunlash hamda 100,000 qatorli sintetik test fayl bilan yuklama sinovini o'tkazish.