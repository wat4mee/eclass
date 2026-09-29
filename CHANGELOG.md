# O'zgarishlar tarixi

## 2026-09-29 (kechqurun): professional daraja, 0–4 bosqichlar

Commit'lar: `2b8111c` (0), `b784a02` (1), `256f98b` (2), `35e0808` (3), `5850a09` (4).

### 0. Topilgan ikki jiddiy xato
- **KaTeX formulalari buzilib yoki bo'sh chiqardi.** Asl sabab: model formulani JSON satri ichida yozadi va ba'zan teskari chiziqni ikkilamaydi. JSON'da `\f`, `\t`, `\b`, `\r`, `\n` maxsus belgilar bo'lgani uchun `\frac` → "form feed" + `rac`, `\to` → tab + `o` bo'lib qolardi (`\times`, `\beta`, `\right`, `\neq` ham shunday). Gemini javobida aynan shu ko'rindi: `\frac{f(a+h)-f(a)}{h}` o'rniga qizil `rac{}{}` chiqdi.
  - `eclass/latex.py` har bir AI javobida bu belgilarni asl LaTeX buyruqlariga qaytaradi (chat, o'quv to'plamlari, boblar, tarjimalar). Oddiy matndagi yangi qator va tab'larga tegilmaydi.
  - Prompt'larga "JSON ichida har bir teskari chiziqni ikkilang" qoidasi qo'shildi.
  - Chat sahifasi: `$...$`, `\(...\)`, `\[...\]` ichidagi qator uzilishi endi formulani ikkiga bo'lmaydi. KaTeX tushunmagan formula bo'sh joy yoki qizil xato o'rniga asl matni bilan ko'rsatiladi (sababi konsolda ogohlantirish sifatida). `\[1\]` endi manba raqami deb o'qilmaydi.
  - Sinov: haqiqiy Gemini bilan 6 ta savol ("Pifagor teoremasini formula bilan yoz", "Limit nima keyin unga misol ber", hosila, masofa, kvadrat tenglama, integral) va soxta javoblarda 8 xil format 390px va 1400px da. Bo'sh paragraf, KaTeX xatosi va konsol xatosi yo'q. Brauzerda sanalgan "bo'sh" elementlar KaTeX'ning oddiy oraliq `span`'lari (`strut`, `mspace`) ekan, ular normal holat.
- **Javobga `found=true` kabi ichki maydon nomlari sizib chiqardi.** Prompt javob maydonlarini alohida tasvirlaydi va "answer matnida boshqa maydonlarni, JSON'ni, true/false'ni eslatma" deydi. Server esa (`rag.clean_answer`) qolgan "found=true" bo'laklarini yoki maydonlar haqidagi gapni olib tashlaydi, oddiy "found" so'zi esa qoladi. 5 ta chegaraviy savolda (dekorator, kvant kompyuter, Nyuton, Java, fotosintez) sizib chiqish bo'lmadi.
- Qo'shimcha: "topilmadi" javobida endi `[2], [6]` kabi manbasiz raqamlar qolmaydi, `[1], [1]` bittaga qisqaradi.

### 1. Kod sifati
- **`eclass/config.py`:** yo'llar (data, baza, fayllar, modellar, lock), eClass manzili, so'rovlar oralig'i, barcha vaqt chegaralari va dashboard oynalari (48 soat "yaqin", 7 kunlik halqa, 4 soat "yangi sync") bitta joyda. `.env` bitta joyda o'qiladi. Kurs ID'lari kodda yo'q, ular har safar dinamik aniqlanadi.
- **N+1 so'rovlar:** chat qidiruvi har bir nomzod bo'lak uchun alohida so'rov yuborardi (bir savolga ~80 ta), endi bitta so'rov. Kurs sahifasi barcha kurslarning har bir videosi uchun alohida so'rov yuborardi, endi bitta.
- **Xatolar bir xil yo'l bilan:** chat, tarjima va bob tayyorlash AI xatolarini `app.ai_failure()` orqali bir xil tushunarli xabarga aylantiradi. To'liq tafsilot faqat serverdagi logga yoziladi.
- Takrorlar olib tashlandi (`clean_text`, `db.pack_columns`). Yangi va o'zgargan funksiyalarda type hint bor.

### 2. Testlar (`tests/`, pytest, 68 ta, 1 soniyadan kam)
- Parserlar (`tests/fixtures/` dagi namuna HTML bilan), baza, `/api/ask` (soxta AI: ko'pi bilan 3 manba, topilmasa manba yo'q, suhbat xotirasi), formula tiklash, qidiruv, ishonchlilik, xavfsizlik. Tarmoq testlarda butunlay o'chirilgan, haqiqiy baza va kalitlarga tegilmaydi.
- **Testlar topgan xatolar (tuzatildi):**
  1. bir soniya ichida ikki marta saqlangan kurs/faoliyat "yangi" deb qayta hisoblanardi;
  2. yangi bazada `/api/chapter` 500 xato berardi (`chapters` jadvali kechiktirib yaratilardi);
  3. Cmd+K indeksi kurslar o'zgarganda yangilanmasdi.
- README'da "Testlarni ishga tushirish" bo'limi.

### 3. Ishonchlilik
- **Sinxronlash xatolari turlarga ajratildi**, har biriga tushunarli sabab bor (3 tilda):
  - login yoki parol noto'g'ri;
  - `.env` da login yo'q;
  - sessiya tugab, qayta kirib bo'lmadi;
  - tarmoq yo'q;
  - vaqt tugadi;
  - eClass serveri xatosi (5xx);
  - sahifa kutilgan ko'rinishda emas.
- **Bitta kurs sahifasi javob bermasa, qolgan kurslar baribir sinxronlanadi.** Buni bugungi haqiqiy hodisa ko'rsatdi: 14:13 dagi avtomatik sync birinchi kurs sahifasida 60 soniyalik vaqt chegarasidan o'tib, butunlay to'xtagan edi.
- **Sinxronlash tarixi:**
  - yangi `sync_runs` jadvali (faqat qo'shildi, eski ma'lumotlar o'zgarmadi) har bir urinishni saqlaydi: vaqt, kim boshlagani, natija, xato turi va parolsiz qisqa tafsilot;
  - bosh sahifa pastidagi "Sinxronlash tarixi" kartasi oxirgi 10 tasini ko'rsatadi;
  - jarayon o'lib qolgan urinish "kutilmaganda to'xtadi" deb chiqadi.
- **AI vaqt chegaralari:**
  - chatda har bir modelga 30 soniya, butun javobga 75 soniya beriladi (sahifa 90 soniya kutadi);
  - sekin yoki javob bermayotgan model o'tkazib yuboriladi va keyingisi javob beradi;
  - hammasi sekin bo'lsa, "AI juda sekin javob bermoqda" xabari chiqadi;
  - o'quv to'plamlari uchun chegara 180 soniya (avvalgidek).
- **`AI_FALLBACK`** (`.env`): zanjir oxiriga qo'shiladigan zaxira modellar. Hozir bo'sh, ya'ni ishlatilmaydi.
- **Matnlar bitta joyda:** Telegram xabarlari va `notify.py --test` endi `eclass/i18n.py` dan olinadi (`NOTIFY_LANGUAGE`, sukut `uz`). Haqiqiy bazada eski va yangi kod bir xil xabar chiqarishi tekshirildi. Har bir matnning uz/en/ru varianti borligini test tekshiradi. Shablonlarda qattiq yozilgan matn qolmagan (faqat "eClass Companion" va "Shahzod AI" nomlari).

### 4. Xavfsizlik tekshiruvi (2)

| Tekshiruv | Natija | Qilingan ish |
|---|---|---|
| Flask 127.0.0.1, debug o'chiq | ✅ | `.env` da `FLASK_DEBUG=0`; test bilan tekshiriladi |
| `.env`, `data/`, `*.db` git tarixida | ✅ yo'q | `git log --all` bo'yicha hech qachon commit qilinmagan. `.env` dagi 5 ta maxfiy qiymatning hech biri tarixda, loglarda, `deploy/` da va sinxronlash tarixida uchramadi (faqat sonlar tekshirildi, qiymatlar chiqarilmadi) |
| `/api/*` faqat lokal, CSRF | ✅ | Host tekshiruvi (DNS rebinding) + POST'da Origin/Referer + faqat JSON; barcha 5 ta POST endpoint uchun test |
| Clickjacking | ⚠️ → ✅ | `X-Frame-Options: DENY` qo'shildi (boshqa sayt dashboard'ni iframe'ga olib, "Sync" tugmasini bostira olmaydi); `nosniff`, `Referrer-Policy: same-origin` |
| Parol/token log va xatolarda | ✅ | eClass xatolari faqat sahifa yo'lini yozadi; sync tafsilotida parol `***` bilan almashtiriladi (test); Telegram va AI kalitlari faqat sarlavhada |
| SQL injection | ✅ | barcha so'rovlar parametrli; FTS qidiruv so'zlari tirnoq ichida; 7 xil hujum matni bilan test |
| XSS | ✅ | Jinja autoescape; JS'da `esc()`; eClass'dan kelgan `<script>` nomli kurs bilan test. Qidiruv natijasi havolasi ham escape qilinadi |
| Path traversal | ✅ | `/file/<int:id>` faqat ID bilan, yo'l `data/files/` ichida ekani tekshiriladi (test: `../`, `/etc/hosts`). Video havolasi faqat `http(s)` bo'lsa yo'naltiriladi (`javascript:` bloklandi) |
| `data/` ruxsatlari | ⚠️ → ✅ | papka hamma uchun o'qiladigan edi (755), endi 700; `deploy/install.sh` ham shunday qiladi. `.env` allaqachon 600 |
| Kutubxonalar | ✅ | `requirements.txt` o'rnatilgan versiyalarga qulflandi (faqat to'g'ridan-to'g'ri ishlatiladiganlar); `pip-audit` ishga tushirilmadi |

### Men tanlagan sukut qiymatlar
- `AI_FALLBACK` bo'sh: hozirgi `.env` zanjirida allaqachon 2 ta Gemini modeli bor. Groq kaliti ham bor, shuning uchun kerak bo'lsa `AI_FALLBACK=groq:openai/gpt-oss-120b` qo'yish mumkin.
- Chat: bitta modelga 30 soniya, butun javobga 75 soniya. O'quv to'plamlari: 180 soniya (o'zgarmadi). eClass: 60 soniya (o'zgarmadi).
- Telegram tili `uz`.
- Sozlamalar sahifasi yo'qligi uchun sinxronlash tarixi bosh sahifaning pastiga qo'yildi.
- Noto'g'ri LaTeX `$...$` bilan asl matn ko'rinishida qoladi: qizil xato ham, bo'sh joy ham chiqmaydi.

### Keyingi safar e'tibor bering
- **Dashboard qayta ishga tushirilishi kerak:** `launchctl kickstart -k gui/$(id -u)/com.eclass.web`. Bu buyruq sessiyada bloklandi. Shu paytgacha 5050-portdagi dashboard eski kodda ishlaydi. Avtomatik sync va eslatmalar yangi kodni o'zi oladi.
- **GitHub:** bu bosqichlarning 6 ta commit'i hali GitHub'da yo'q (`origin/main` = `bd6d1a0`). Yuborish: `git push origin main`.
- Groq, Telegram va Gemini kalitlarini almashtirish tavsiyasi hali ham amalda.
- CSP sarlavhasi qo'shilmadi (sahifalarda inline skriptlar ko'p). `pip-audit` bilan kutubxonalarni tekshirish mumkin.
- Model ba'zan LaTeX'ni xato yozadi (masalan `$[a, b$`). Bu modelning xatosi: matn yo'qolmaydi, lekin chiroyli chiqmaydi.
- Bo'sh qolgan agent worktree'si: `git worktree remove .claude/worktrees/agent-ae49f5bc79c3290f8 && git branch -D pro-upgrade`.

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
