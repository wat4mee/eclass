# O'zgarishlar tarixi

## 2026-09-29: A–D bosqichlari, tillar, Shahzod AI, AI zanjiri

### 0. Tillar va nom
- Dashboard to'liq **o'zbek, ingliz va rus** tillarida ishlaydi. Til yuqoridagi 🌐 menyusidan tanlanadi va cookie'da saqlanadi.
- Tarjima qilinganlar: barcha matnlar, sanalar, "3 kun qoldi" kabi vaqtlar, ruscha ko'plik shakllari va xato xabarlari.
- O'quv to'plami boshqa tilda birinchi marta ochilganda fonda tarjima qilinadi va saqlanadi (`study_i18n` jadvali).
- Chat endi **Shahzod AI** deb ataladi va tanlangan tilda javob beradi.

### A. AI chat
- **Suhbat xotirasi:** oxirgi 4 ta savol-javob serverga yuboriladi. Keyingi savol qidiruvdan oldin mustaqil savolga aylantiriladi ("Unga oddiy misol ber" → "Limitga oddiy misol ber").
- **Manbalar:**
  - yaqinlik bahosi 0.68 dan past bo'laklar tashlanadi;
  - ma'lumot topilmasa, manbalar ro'yxati umuman ko'rsatilmaydi;
  - ko'pi bilan 3 ta manba chiqadi, bitta fayl va yaqin sahifalar birlashtiriladi ("141, 142-betlar"), uzun nomlar "…" bilan qisqartiriladi;
  - kitob mundarijasi va dars jadvali kabi sahifalar natijalarda pastga tushiriladi.
- **Xatolar:**
  - "Failed to fetch" va 90 soniyalik timeout ushlanadi, "Qayta urinish" tugmasi chiqadi;
  - serverda AI xatosida 2 soniyadan keyin bir marta avtomatik qayta urinish bor;
  - xato tafsiloti `data/logs/web.log` ga kalitlarsiz yoziladi.
- **Formulalar:** KaTeX va shriftlar lokal (`static/`), ilova internetsiz ishlaydi. Formulalar `$...$` va `$$...$$` ichida chiroyli ko'rsatiladi.
- **Til sifati:** prompt'larga o'zbekcha yozish qoidalari qo'shildi: texnik atamalar inglizcha qoladi, so'zma-so'z tarjima qilinmaydi, javoblar qisqa.

### B. Sinxronlash va eslatmalar
- **"Oxirgi sinxronlash" tugmasi** bosiladi va sync'ni fonda ishga tushiradi:
  - bir vaqtda faqat bitta sync ishlaydi;
  - jarayon holati ko'rsatiladi;
  - tugagach, yangi material, topshiriq va baholar ro'yxati chiqadi;
  - xato bo'lsa, sababi bilan qizil ogohlantirish chiqadi (login o'zgargan, eClass ishlamayapti, kutilmagan xato). Launchd'dagi avtomatik sync xatolari ham shunday ko'rsatiladi.
- **`deploy/install.sh`** 3 ta launchd agentini o'rnatadi: sync har 3 soatda, eslatmalar har 30 daqiqada, dashboard doim yoqiq. Yo'riqnoma README.md'da.
- **Telegram:**
  - muddatga 24 soat va 3 soat qolganda eslatma yuboriladi;
  - yangi material, topshiriq va baho haqida xabar keladi;
  - hech bir xabar takrorlanmaydi;
  - token bo'lmasa, bu qism jimgina o'tkazib yuboriladi.

### C. Yangi funksiyalar
- **Topshiriq fayllari** (lab1.pdf, rubrikalar va hokazo) uchun ham o'quv to'plami yaratiladi.
- **Katta darsliklar** mundarija bo'yicha (bo'lmasa har 30 betda) boblarga bo'linadi. "Boblar" tugmasi bor. Bob to'plami "Tayyorlash" bosilganda fonda yaratiladi va qayta yaratilmaydi.
- **YouTube video darslar:** transkript olinadi va unga ham xulosa, kartalar, test va Shahzod AI qidiruvi ishlaydi. Transkript bo'lmasa, "Transkript mavjud emas" deb yoziladi.
- **Global qidiruv (⌘K, Ctrl+K yoki `/`):** SQLite FTS5 asosida kurslar, topshiriqlar, fayllar, o'quv to'plamlari va boblar bo'yicha qidiradi. Mos joylar ajratilib, kurs nomi bilan chiqadi.
- **"Bugun nima qilish kerak" bloki:** yaqin muddatlar, oxirgi o'rganilmagan material va bitta tavsiya. Materialni "O'rganildi" deb belgilash mumkin (`progress` jadvali).
- **Baholar kurs bo'yicha guruhlangan:** to'plangan ball, foiz va o'rtacha ko'rsatiladi. Baholanmaganlar alohida chiqadi, muddati yo'qlarida aniq "Muddatsiz" deb yoziladi.

### AI zanjiri (bepul limit tugab qolmasligi uchun)
- `AI_PROVIDER=auto`: Groq `gpt-oss-120b` → `qwen3.8-27b` → `gpt-oss-20b` → Gemini `gemini-3.8-flash` → Ollama. Birining kunlik limiti tugasa, keyingisiga avtomatik o'tiladi.
- Kalit rad etilsa ham (bekor qilingan, xato yozilgan yoki boshqa qatorga yozilgan: 401/403), zanjir o'sha provayderni o'tkazib, keyingisiga o'tadi.
- Model band bo'lsa (503, daqiqalik 429 yoki "request too large"), zanjir kutib o'tirmasdan keyingi modelga o'tadi. Faqat zanjirdagi oxirgi model qisqa kutib, qayta urinadi. Gemini'ning "retry in 41s" ko'rinishidagi kutish vaqti ham o'qiladi. Oldin Groq `qwen` modeli 1000 tokenlik chiqish limiti tufayli har bir savolda 21 soniyadan bir necha marta kuttirardi.
- **Hozirgi sozlama: faqat Gemini.** `.env` da `AI_PROVIDER=gemini:gemini-3.5-flash-lite,gemini:gemini-3.5-flash`. `gemini-3.8-flash` tez-tez band bo'lgani uchun (503/429) sukut bo'yicha model `gemini-3.5-flash-lite` qilindi: sinovlarda eng tez va eng barqaror chiqdi. Chat javobi o'rtacha 4–9 soniya oladi, oldin 47 soniya olardi.
- `.env.example` ga qo'shimcha sozlamalar va ularning sukut bo'yicha qiymatlari qo'shildi.

### D. Ko'rinish va xavfsizlik
- 404 va 500 uchun ilova dizaynidagi sahifalar tayyor, 3 tilda. `/api/*` xatolari JSON ko'rinishida qaytadi.
- Test natija ekrani va "Qaytadan" tugmasi tekshirildi va ishlaydi.

## Xavfsizlik tekshiruvi hisoboti

| Tekshiruv | Natija | Qilingan ish |
|---|---|---|
| Flask faqat 127.0.0.1'da | ✅ | `app.run(host="127.0.0.1")`; `lsof` faqat `127.0.0.1:5050` ni ko'rsatdi |
| debug o'chiq | ✅ | endi faqat `.env`'da `FLASK_DEBUG=1` bo'lsa yoqiladi, sukut bo'yicha o'chiq |
| `.env`, `data/`, `*.db` gitignore'da | ✅ | `*.db-wal`, `*.db-shm`, `.DS_Store` ham qo'shildi; `git log --all -- .env` bo'sh, kuzatilayotgan fayllar orasida maxfiy fayl yo'q |
| cookie/sessiya fayllari | ✅ | eClass sessiyasi faqat xotirada saqlanadi, diskka yozilmaydi |
| AI'ga ma'lumot yuborilishi | ✅ | README'da aniq yozildi, jumladan Gemini bepul tarifida Google ma'lumotlardan foydalanishi |
| Parol va token loglarda | ✅ | `data/logs/*` da Groq, Gemini, Telegram kalitlari va eClass paroli topilmadi. Xato sahifalarida traceback ko'rinmaydi |
| CSRF / origin | ✅ yangi | `/api/*` POST so'rovlarida `Origin`/`Referer` tekshiriladi, boshqa saytdan kelganlari 403 oladi. Begona `Host` sarlavhasi 400 oladi (DNS rebinding himoyasi) |

**Tavsiya:** Groq, Telegram va Gemini kalitlari suhbat davomida chatga yozilgan. Ularni tegishli paneldan yangilab, yangisini to'g'ridan-to'g'ri `.env`'ga yozing.

## Qanday ishga tushiriladi

```bash
.venv/bin/pip install -r requirements.txt
./deploy/install.sh                  # sync, eslatmalar va dashboard avtomatik ishlaydi
open http://127.0.0.1:5050
.venv/bin/python tests/e2e.py smoke  # tekshirish (Playwright)
```

## Qolgan ishlar va cheklovlar
- **Kitob boblari:** hozircha hech biri tayyorlanmagan. Bepul AI limiti tufayli ular faqat "Tayyorlash" bosilganda, bittadan yaratiladi (bir bob taxminan 5 daqiqa oladi).
- **Video va topshiriq to'plamlari:** AI limiti bo'shaganda avtomatik sync'da yaratiladi. Bir qismi tayyor, qolganlari navbatda.
- **Bob to'plamlari tarjimasi:** ular `STUDY_LANGUAGE` tilida yaratiladi va boshqa tillarga tarjima qilinmaydi (fayl to'plamlari tarjima qilinadi).
- **3 soatlik eslatma aniqligi:** topshiriq holati oxirgi sync'dan olinadi. Ishni sync'lar orasida topshirsangiz, eslatma baribir kelishi mumkin.
- **YouTube:** kelajakda transkript so'rovlarini bloklashi mumkin. Unda "Transkript mavjud emas" chiqadi, xato bermaydi.
- **Server:** dashboard Flask'ning ishlab chiqish serverida ishlaydi. Faqat lokal foydalanish uchun bu yetarli.
