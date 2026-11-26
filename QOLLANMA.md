# Mat-Hisobot — Windows tizimiga ko'chirish va ishga tushirish qo'llanmasi

Ushbu qo'llanma loyihani Docker orqali istalgan **Windows 10 / 11** kompyuteriga ko'chirish va ishga tushirish uchun mo'ljallangan.

---

## 1-qadam. Windows'da Docker Desktop o'rnatish

1. Rasmiy saytdan **Docker Desktop for Windows** ni yuklab olib o'rnating:
   https://www.docker.com/products/docker-desktop/
2. O'rnatish jarayonida **Use WSL 2 instead of Hyper-V** bandi belgilangan bo'lsin.
3. Kompyuterni qayta yoqing va **Docker Desktop** dasturini ishga tushiring (pastki chap burchakda yashil **Engine running** yozuvi paydo bo'lishi kerak).
4. **PowerShell** ochib tekshiring:
   ```powershell
   docker --version
   docker compose version
   ```

---

## 2-qadam. Loyihani Linux'dan Windows'ga ko'chirish

Quyidagi 2 usuldan birini tanlang (**B-usul** tezroq va Windows'da internet talab qilmaydi):

### A-usul — Windows'da internet bor bo'lsa (loyiha papkasini ko'chirish)

Linux kompyuterda ortiqcha fayllarsiz ZIP arxiv yarating va flashka orqali Windows'ga o'tkazing:

```bash
cd /home/asus/Desktop/MY_Projects/Mat-Hisobot
zip -r ~/Mat-Hisobot.zip . -x ".git/*" ".venv/*" ".pgdata/*" "media/*" "staticfiles/*" ".env" "*.xlsx"
```

Windows'da arxivni masalan `C:\Projects\Mat-Hisobot` papkasiga oching.

### B-usul — Windows'da internet sekin yoki yo'q bo'lsa (tayyor Docker image bilan)

1. **Linux kompyuterda** image'larni bitta faylga eksport qiling:
   ```bash
   docker pull postgres:16-alpine
   docker save mat-hisobot:latest postgres:16-alpine -o ~/mat-hisobot-images.tar
   ```
2. Windows'dagi `C:\Projects\Mat-Hisobot\` papkasiga faqat **3 ta fayl**ni ko'chiring:
   - `mat-hisobot-images.tar`
   - `docker-compose.yml`
   - `.env.example`

---

## 3-qadam. `.env` konfiguratsiya faylini sozlash

Windows **PowerShell** da loyiha papkasiga o'ting va `.env` yarating:

```powershell
cd C:\Projects\Mat-Hisobot
Copy-Item .env.example .env
notepad .env
```

Notepad ichida qiymatlarni o'zingizga moslab saqlang:

```env
SECRET_KEY=uzun-tasodifiy-50-ta-belgidan-kop-maxfiy-kalit-2026-win
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=
SECURE_SSL_REDIRECT=False
APP_PORT=8000

DB_NAME=mat_hisobot
DB_USER=postgres
DB_PASSWORD=KuchliParol2026!

DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=AdminParol2026!

GEMINI_API_KEY=
```

> **Lokal tarmoqda boshqa kompyuterlardan kirish uchun:** Windows kompyuterning IP manzilini `ipconfig` orqali aniqlang va `ALLOWED_HOSTS` ga qo'shing, masalan:
> `ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.50`

---

## 4-qadam. Loyihani ishga tushirish

- **A-usul** (ZIP papka) bo'yicha:
  ```powershell
  docker compose up -d --build
  ```
- **B-usul** (`.tar` image) bo'yicha:
  ```powershell
  docker load -i mat-hisobot-images.tar
  docker compose up -d --no-build
  ```

Konteynerlar holatini tekshiring (`db`, `web`, `worker` barchasi `Up` / `healthy` bo'lishi kerak):

```powershell
docker compose ps
```

Brauzerda oching: **`http://localhost:8000`**
Kirish uchun `.env` faylida ko'rsatilgan `DJANGO_SUPERUSER_USERNAME` va `DJANGO_SUPERUSER_PASSWORD` dan foydalaning.

---

## 5-qadam. Kundalik boshqaruv buyruqlari (PowerShell)

| Vazifa | Buyruq |
|---|---|
| To'xtatish (ma'lumotlar bazasi saqlanadi) | `docker compose stop` |
| Qayta ishga tushirish | `docker compose start` |
| Loglarni jonli ko'rish | `docker compose logs -f web worker` |
| Yangi admin qo'shish | `docker compose exec web python manage.py createsuperuser` |
| Ma'lumotlar bazasidan zaxira olish (backup) | `docker compose exec db pg_dump -U postgres mat_hisobot > backup.sql` |
| Zaxiradan tiklash (restore) | `Get-Content backup.sql \| docker compose exec -T db psql -U postgres -d mat_hisobot` |
| Konteynerlarni o'chirish (bazani saqlab) | `docker compose down` |

---

## Ehtimoliy muammolar va yechimlar

1. **8000-port band (`Bind for 0.0.0.0:8000 failed`):**
   `.env` faylida `APP_PORT=8080` qiling va `docker compose up -d` ni qayta ishga tushiring (`http://localhost:8080`).
2. **Windows'da `bash\r: No such file or directory` xatosi:**
   `docker-entrypoint.sh` fayli Git yoki Notepad orqali `CRLF` formatiga o'zgargan bo'lsa yuz beradi. VS Code / Notepad++ da qator oxirini **LF (Unix)** qilib saqlang va `docker compose up -d --build` ni qayta bajaring (B-usulda bu xato uchramaydi).
3. **Konteynerlar o'chib ketmasligi:**
   Barcha konteynerlarda `restart: unless-stopped` o'rnatilgan; Windows qayta yonganda Docker Desktop ishga tushishi bilan loyiha ham avtomatik yonadi.
