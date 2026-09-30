# sclass'ni Render'ga joylash

Bu qo'llanma sayt versiyasini (`web/` papkasi, `hosted` branch) internetga chiqaradi. Mac versiyasiga
(`app.py`, launchd) ta'sir qilmaydi.

Nima bo'ladi:

| Qism | Qayerda | Narxi |
|---|---|---|
| Sayt (`sclass`) | Render, web service | bepul (`free`); 15 daqiqa ishlatilmasa uxlaydi |
| Fon sinxronlash | GitHub Actions har 3 soatda saytni chaqiradi (9-bo'lim) | bepul |
| Ma'lumotlar bazasi | Neon Postgres | bepul tarif yetadi |
| AI | Google Gemini | bepul limit, barcha talabalar uchun umumiy |

Hamma sozlamalar `render.yaml` faylida yozilgan, qo'lda kiritiladigani faqat 3 ta maxfiy qiymat.

---

## 0. Kodni GitHub'ga yuklash

```bash
git push -u origin hosted
```

Render kodni GitHub'dan oladi: `hosted` branch u yerda bo'lishi kerak.

## 1. Neon: ma'lumotlar bazasi

1. [neon.tech](https://neon.tech) da ro'yxatdan o'ting, **New Project** bosing.
2. Nomi: `sclass`. **Region: AWS Europe Central 1 (Frankfurt)**: Render xizmati ham Frankfurtda, shunda baza yaqin bo'ladi.
3. Loyiha ochilgach **Connect** tugmasini bosing:
   - **Connection pooling ni O'CHIRING** (direct connection). Muhim: sayt va cron bitta talabani bir vaqtda
     sinxronlamasligi uchun Postgres lock ishlatiladi, u pooling orqali ishlamaydi.
   - Chiqqan satrni nusxalang, taxminan shunday bo'ladi:
     `postgresql://USER:PAROL@ep-xxxx.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require`
   - Bu **DATABASE_URL**. Ichida parol bor: hech kimga yubormang, kodga yozmang.

Jadvallarni o'zingiz yaratmaysiz: sayt har ishga tushganda `alembic upgrade head` o'zi bajaradi.

## 2. CREDENTIAL_KEY: shifrlash kaliti

Talabalar "Fonda sinxronlab tur" ni yoqsa, ularning paroli shu kalit bilan shifrlanadi. Kalit faqat Render
sozlamalarida turadi: bazada ham, kodda ham yo'q.

Kompyuteringizda yarating:

```bash
cd "/Users/muhammadshahzod/all codes/eclass"
.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

- Chiqqan qatorni **parol menejeriga** (yoki xavfsiz joyga) saqlang.
- Yo'qolsa, saqlangan parollarni ochib bo'lmaydi: talabalar parolni qayta kiritishga majbur bo'ladi (ma'lumotlar
  yo'qolmaydi).
- `.env` dagi `CREDENTIAL_KEY` faqat Mac'da sinash uchun: Render uchun **yangisini** yarating.

## 3. Gemini API kaliti

[aistudio.google.com](https://aistudio.google.com) → **Get API key**. Eskisi chatda ko'rsatilgan bo'lsa, yangi
kalit oling. Bu **GEMINI_API_KEY**.

## 4. Render: Blueprint

1. [render.com](https://render.com) da GitHub orqali ro'yxatdan o'ting. Blueprint pullik cron'ni ham yaratadi, shuning
   uchun **karta** so'raladi. Bepul yo'l: faqat web service'ni qo'lda yarating, fon sinxronlashni esa GitHub Actions
   bajaradi (9-bo'lim).
2. **New → Blueprint** → repozitoriyni tanlang → branch: **`hosted`**. Render `render.yaml` ni o'qib, ikkita xizmatni
   (`sclass`, `sclass-sync`) va `sclass-settings` sozlamalar guruhini ko'rsatadi.
3. U 3 ta qiymatni **har bir xizmat uchun alohida** so'raydi. Ikkalasiga **bir xil** qiymat kiriting:

   | Kalit | Qiymat |
   |---|---|
   | `DATABASE_URL` | 1-qadamdagi Neon satri |
   | `CREDENTIAL_KEY` | 2-qadamdagi kalit |
   | `GEMINI_API_KEY` | 3-qadamdagi kalit |

   `SECRET_KEY` ni Render o'zi yaratadi. `HOSTED`, `AI_PROVIDER`, `STUDY_LANGUAGE` va boshqalar `render.yaml` da bor.
4. **Apply** bosing. Birinchi build 3–5 daqiqa oladi. `sclass` loglarida oxirida shunday qatorlar chiqishi kerak:
   `Running upgrade -> 9badf696a03d, initial schema` va `Listening at: http://0.0.0.0:10000`.

## 5. Tekshirish

1. `https://sclass.onrender.com/healthz` → `{"status":"ok"}` (nom band bo'lsa, Render boshqa nom beradi, masalan
   `sclass-ab12.onrender.com`: sayt uni o'zi taniydi).
2. Saytga eClass login bilan kiring: kurslar 1–3 daqiqada paydo bo'ladi.
3. **Hisob** sahifasida "Fonda sinxronlash" ni yoqing.
4. Render → `sclass-sync` → **Trigger Run**. Logda `scheduled sync: {'students': 1, 'done': 1, ...}` chiqishi kerak.

## 6. Kundalik ishlar

- **Kodni yangilash:** `hosted` branch'ga push qiling, Render ikkala xizmatni o'zi qayta joylaydi.
- **O'z domeningiz:** Render → `sclass` → Settings → Custom Domains. Keyin `sclass` xizmatiga
  `ALLOWED_HOSTS=sizning.domeningiz` qo'shing (onrender.com nomi baribir ishlayveradi).
- **Uxlab qolmasin desangiz:** `render.yaml` da `sclass` uchun `plan: free` ni `plan: 0.5c-512mb` ga o'zgartiring.
  Bepul tarifda uxlagan sayt birinchi so'rovda ~1 daqiqada uyg'onadi.
- **Limitlar:** `render.yaml` dagi `AI_DAILY_LIMIT` (talaba boshiga kunlik savol), `PACKS_PER_RUN` (har cron
  tayyorlaydigan o'quv to'plami).

## 7. CREDENTIAL_KEY ni almashtirish (rotation)

Kalit oshkor bo'lgan deb gumon qilsangiz yoki muntazam xavfsizlik uchun:

1. Yangi kalit yarating (2-qadamdagi buyruq).
2. **Ikkala xizmatda** Environment bo'limida:
   - `CREDENTIAL_KEY_PREVIOUS` = eski kalit (yangi qator);
   - `CREDENTIAL_KEY` = yangi kalit.

   `render.yaml` da `CREDENTIAL_KEY_VERSION` ni `"2"` qilib push qiling (keyingi safar `"3"` va hokazo).
3. Joylash tugagach, saqlangan parollarni yangi kalitga o'tkazing. Buni Mac'dan Neon bazasiga qarshi bajarasiz:

   ```bash
   DATABASE_URL='<Neon satri>' CREDENTIAL_KEY='<yangi>' CREDENTIAL_KEY_PREVIOUS='<eski>' CREDENTIAL_KEY_VERSION=2 \
     .venv/bin/flask --app web rotate-credentials
   ```

   Natija: `re-encrypted N password(s) and M session(s); dropped 0 ...`
4. Ikkala xizmatdan `CREDENTIAL_KEY_PREVIOUS` ni o'chiring.

## 8. Muammolar

| Belgi | Sabab va yechim |
|---|---|
| Build xato bilan tugadi | Render logini oching; odatda `requirements-web.txt` dagi paket. Python versiyasi `.python-version` da (3.14). |
| `ConfigError: DATABASE_URL is not set` (yoki `CREDENTIAL_KEY`) | Shu xizmatning Environment bo'limida qiymat yo'q: qo'shing va **Manual Deploy** bosing. |
| `CREDENTIAL_KEY is not a valid Fernet key` | Kalitni to'liq nusxalamagansiz (44 belgi, oxiri `=`). |
| Bazaga ulanib bo'lmaydi | `DATABASE_URL` da `sslmode=require` bormi, pooling o'chirilganmi (1-qadam). |
| Sayt "400 Bad Request" beradi | O'z domeningizdan ochyapsiz: `ALLOWED_HOSTS` ga qo'shing (6-qadam). |
| Hamma talabalarda "eClass javob bermayapti" | eClass Render IP manzilini cheklagan bo'lishi mumkin: bir necha soatdan keyin qayta ko'ring; cron ketma-ket 3 ta xatodan keyin o'zi to'xtaydi. |
| AI "limit tugadi" deydi | Gemini bepul limiti tugagan (hamma uchun umumiy): ertasi kuni tiklanadi. |

## 9. Bepul tarifda avtomatik sinxronlash (GitHub Actions)

Render'ning bepul tarifida Cron Job yo'q (u doim kamida $1/oy). Shuning uchun har 3 soatda GitHub Actions saytdagi
himoyalangan `POST /internal/sync-all` manzilini chaqiradi. Sayt darhol `202 {"status": "started"}` qaytaradi va
"Fonda sinxronlab tur" ni yoqqan talabalarni o'zining fon navbatida birma-bir sinxronlaydi.

1. **CRON_SECRET yarating** (uzun tasodifiy matn; hech kimga ko'rsatmang):
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. **Render:** `eclass` xizmati → **Environment** → **Add Environment Variable**: Key `CRON_SECRET`, Value yuqoridagi
   matn → **Save Changes** (xizmat qayta joylanadi). `CRON_SECRET` bo'lmasa yoki 16 belgidan qisqa bo'lsa, manzil
   o'chiq turadi va 503 qaytaradi.
3. **GitHub** (repo → **Settings → Secrets and variables → Actions**):
   - **Secrets** yorlig'i → **New repository secret**: Name `CRON_SECRET`, qiymati Render'dagi bilan **aynan bir xil**;
   - **Variables** yorlig'i → **New repository variable**: Name `RENDER_URL`, qiymati `https://eclass-zrs8.onrender.com`.

   GitHub CLI o'rnatilgan bo'lsa, xuddi shu ish:
   ```bash
   gh secret set CRON_SECRET          # qiymatni so'raydi, ekranga chiqarmaydi
   gh variable set RENDER_URL --body https://eclass-zrs8.onrender.com
   ```
4. **Workflow default branch'da bo'lishi shart.** GitHub jadval bo'yicha va qo'lda ishga tushirishni faqat default
   branch'dagi `.github/workflows/sync-cron.yml` dan bajaradi. Default branch `main` bo'lsa:
   ```bash
   git checkout main && git merge --ff-only hosted && git push origin main && git checkout hosted
   ```
   (yoki GitHub → Settings → General → Default branch'ni `hosted` qiling).
5. **Tekshirish:** GitHub → **Actions** → **sclass sync** → **Run workflow**. Yashil bo'lishi kerak. Render logida:
   `sync-all accepted: started`, keyinroq `scheduled sync of all students: {'students': N, 'done': N, ...}`.

Bilib qo'ying:
- Ish muvaffaqiyatsiz bo'lsa (noto'g'ri token → 401, sozlanmagan → 503, sayt javob bermadi), workflow qizil bo'ladi va
  GitHub xat yuboradi. Xat workflow faylidagi `cron` qatorini oxirgi o'zgartirgan foydalanuvchiga boradi.
- GitHub band paytlarda ishni bir necha daqiqa kechiktirishi mumkin. Ochiq (public) repoda 60 kun hech qanday faollik
  bo'lmasa, jadval o'chib qoladi: Actions sahifasida qayta yoqasiz.
- Bepul Render sayti oxirgi so'rovdan 15 daqiqa keyin uxlaydi. Talabalar ko'p bo'lsa, uzun sinxronlash yarmida uzilishi
  mumkin. Keyingi safar eng uzoq sinxronlanmagan talabalardan boshlanadi, shuning uchun hech kim doim oxirida qolmaydi.
- Manzil daqiqasiga 1 marta chaqiriladi (ko'prog'i 429). Token doimiy vaqtda solishtiriladi va loglarga yozilmaydi.
- `CRON_SECRET` ni almashtirsangiz, Render'da ham, GitHub'da ham yangilang.
- **`render.yaml` dagi cron hozir ishlatilmaydi.** Pullik tarifga o'tsangiz, Render'da Cron Job yarating
  (`python -m web.sync --all`, `render.yaml` dagi ta'rif bo'yicha) va `.github/workflows/sync-cron.yml` ni o'chiring.
  Unda sinxronlash sayt ichida emas, alohida xizmatda ishlaydi va saytni sekinlashtirmaydi.

## Xavfsizlik eslatmalari

- `DATABASE_URL`, `CREDENTIAL_KEY`, `GEMINI_API_KEY` ni hech qachon kodga, chatga yoki skrinshotga qo'ymang.
- Talabalarni taklif qilishdan oldin INHA IT bo'limidan so'rab ko'ring: sayt talabalarning universitet parollari bilan
  ishlaydi (norasmiy loyiha ekanligi saytda yozilgan).
- Talaba **Hisob → Ulanishni uzish va ma'lumotlarimni o'chirish** orqali o'zi haqidagi hamma narsani o'chira oladi.
