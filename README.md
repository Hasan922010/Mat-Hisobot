# Mat-Hisobot

Korxonalar uchun **TMQ (Materiallar Hisoboti), Kirimsiz Sotuvlar va Raqamli Markirovka (Asl Belgisi / DataMatrix)** tahlil platformasi.

## Texnologik stek
- **Backend:** Django 6 + Django REST Framework + PostgreSQL 16+ + Django-Q2 (ORM broker) + Gunicorn
- **Data & Export:** Pandas, NumPy, OpenPyXL, xlrd, RapidFuzz, `google-genai`
- **Frontend:** Django Templates + Tailwind CSS + HTMX + Alpine.js (offline vendored assets)

## Netlify’da ishlatish

Netlify deploy bosh sahifada audit ish maydonini ochadi. Netlify Identity orqali kiring yoki ro‘yxatdan o‘tish ochiq bo‘lsa hisob yarating. Alohida kirim va chiqim hujjatlarini yoki bitta umumiy `.xlsx`, `.xls` yoki `.csv` faylini yuklang (har bir fayl 10 MB gacha). Natija tayyor bo‘lgach, qoldiqlarni, kirimsiz sotuvlarni va markirovka tafovutlarini ko‘ring yoki Excel hisobotini yuklab oling.

Netlify Database hisobot yozuvlarini, Netlify Blobs esa manba va eksport fayllarini saqlaydi. Hisobotlarni faqat ularni yaratgan foydalanuvchi ko‘ra oladi. Audit va Excel eksporti mavjud Python hisoblash kodidan foydalanadi. Django hisoblari va oldingi hisobotlar avtomatik ko‘chirilmaydi; Docker orqali ishlatish tartibi o‘zgarmagan.

Netlify auditini tekshirish: `npm ci` va `npm test` (Node.js 24+).

## Docker orqali ishga tushirish (boshqa har qanday tizimda)

1. Loyiha papkasini yangi server/kompyuterga ko'chiring va `.env.example` dan `.env` yarating:
   ```bash
   cp .env.example .env
   # .env ichida SECRET_KEY, DB_PASSWORD, DJANGO_SUPERUSER_PASSWORD va ixtiyoriy GEMINI_API_KEY ni o'zgartiring
   ```
2. Barcha servislarni (PostgreSQL + Django Web + Django-Q2 Worker) ishga tushiring:
   ```bash
   docker compose up -d --build
   ```
3. Brauzerda oching: `http://localhost:8000` (yoki `.env` dagi `APP_PORT`).

### Offline (internetsiz) tizimga ko'chirish
```bash
# 1. Joriy kompyuterda image yaratish va arxivlash:
docker compose build
docker save mat-hisobot:latest postgres:16-alpine | gzip > mat-hisobot-images.tar.gz

# 2. Yangi kompyuterda yuklash va ishga tushirish:
docker load < mat-hisobot-images.tar.gz
docker compose up -d
```

## Mahalliy (Dockersiz) ishga tushirish
```bash
./run.sh        # yoki ./run.sh 8005
```

## Testlar va tekshiruv
```bash
uv run pytest -v
uv run python manage.py check
```

## Production (HTTPS) eslatmalari
- Nginx / Caddy / Traefik ortida HTTPS yoqilganda `.env` da `DEBUG=False`, `SECURE_SSL_REDIRECT=True`, `ALLOWED_HOSTS=hisobot.example.uz` va `CSRF_TRUSTED_ORIGINS=https://hisobot.example.uz` o'rnating.
