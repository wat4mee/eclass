# eClass Companion

INHA University in Tashkent eClass tizimi uchun shaxsiy yordamchi. U quyidagilarni qiladi:

- kurs materiallari, topshiriqlar va baholarni avtomatik yuklab oladi;
- har bir material uchun AI yordamida qisqa mazmun, kartalar va test tayyorlaydi;
- "Shahzod AI" chatida materiallar bo'yicha savollarga manbasi bilan javob beradi (formulalar KaTeX bilan);
- muddatlar va yangiliklar haqida Telegram'ga eslatma yuboradi;
- hammasini lokal dashboard'da ko'rsatadi: http://127.0.0.1:5050 (o'zbek, ingliz va rus tillarida).

> **Do'stlar uchun:** qadamma-qadam o'rnatish va foydalanish qo'llanmasi (texnik bilim talab qilinmaydi): **[QOLLANMA.md](QOLLANMA.md)**.
> Dasturni birovga berishdan oldin uning oxiridagi "Dasturni do'stingizga berish" bo'limini o'qing: papkaning o'zini bermang, unda parolingiz bor.
>
> **Sayt versiyasi (sclass):** ko'p talabali sayt `web/` papkasida (`hosted` branch). Render + Neon'ga joylash: **[DEPLOY.md](DEPLOY.md)**.

## O'rnatish (yangi kompyuterda)

Kerak: macOS, Python 3.11 yoki yangiroq (sinovdan o'tgan: 3.14), internet.

```bash
git clone <repo-manzili> eclass && cd eclass
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt      # kutubxonalar versiyalari qulflangan
cp .env.example .env                           # keyin .env ni to'ldiring (pastga qarang)
chmod 600 .env                                 # parol faqat sizga ko'rinsin
.venv/bin/python sync.py --all                 # birinchi sinxronlash (bir necha daqiqa)
.venv/bin/python app.py                        # dashboard: http://127.0.0.1:5050
```

Doim ishlab tursin desangiz: `./deploy/install.sh` (pastda "Avtomatik ishga tushirish").

## Sozlamalar (`.env`)

`.env` fayli faqat shu kompyuterda turadi va git'ga tushmaydi. Namuna: `.env.example` (unda haqiqiy qiymatlar yo'q).

| O'zgaruvchi | Majburiy | Ma'nosi |
|---|---|---|
| `ECLASS_USER`, `ECLASS_PASS` | ha | eClass login va paroli |
| `AI_PROVIDER` | yo'q | `auto` (sukut), `groq`, yoki ro'yxat: `gemini:gemini-3.5-flash-lite,gemini:gemini-3.5-flash` |
| `GROQ_API_KEY` | AI uchun | https://console.groq.com dan bepul kalit |
| `GEMINI_API_KEY` | yo'q | https://aistudio.google.com/apikey dan bepul kalit; `GEMINI_MODEL` sukut bo'yicha `gemini-3.5-flash-lite` |
| `AI_FALLBACK` | yo'q | zaxira modellar: `AI_PROVIDER` dagi hamma model ishlamasa yoki juda sekin bo'lsa, oxirida shular sinab ko'riladi. Format `AI_PROVIDER` bilan bir xil, masalan `groq:openai/gpt-oss-120b,ollama`. Sukut: bo'sh |
| `AI_TIMEOUT` | yo'q | o'quv to'plamlari uchun bitta AI so'rovining vaqt chegarasi, soniya (sukut: 180) |
| `AI_CHAT_TIMEOUT`, `AI_CHAT_BUDGET` | yo'q | chatda bitta model uchun (30) va butun javob uchun (75) soniya. Sekin model o'tkazib yuboriladi |
| `ECLASS_TIMEOUT` | yo'q | eClass'ga bitta so'rovning vaqt chegarasi, soniya (sukut: 60) |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | yo'q | yo'q bo'lsa, Telegram eslatmalari jimgina o'tkazib yuboriladi |
| `NOTIFY_LANGUAGE` | yo'q | Telegram xabarlari tili: `uz` (sukut), `en`, `ru` |
| `STUDY_LANGUAGE` | yo'q | o'quv to'plamlari tili: `uz` (sukut), `en`, `ru` |
| `EMBED_THREADS` | yo'q | qidiruv indeksi uchun CPU yadrolari (sukut: 2) |
| `ECLASS_TZ` | yo'q | muddatlar vaqt mintaqasi (sukut: `Asia/Tashkent`) |
| `FLASK_DEBUG` | yo'q | `1` bo'lsa Flask debug rejimi yoqiladi. Sukut bo'yicha o'chiq; yoqiq qoldirmang |

Qolgan sozlamalar (`GROQ_MODEL`, `GROQ_TPM`, `OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT`) va ularning sukut qiymatlari `.env.example` da yozilgan. Barcha vaqt chegaralari va yo'llar bitta joyda: `eclass/config.py`.

**AI zanjiri.** Bepul limitlar tugab qolmasligi uchun modellar navbat bilan ishlatiladi. `AI_PROVIDER=auto` da:
Groq `gpt-oss-120b` → Groq `qwen3.8-27b` → Groq `gpt-oss-20b` → Gemini (kalit bo'lsa) → Ollama (ishlayotgan bo'lsa), keyin `AI_FALLBACK`.
Birining kunlik limiti tugasa, kalit rad etilsa, model band bo'lsa yoki vaqt chegarasida javob bermasa, zanjir keyingisiga o'tadi.
Faqat Gemini ishlatish uchun (tez va barqaror): `AI_PROVIDER=gemini:gemini-3.5-flash-lite,gemini:gemini-3.5-flash`.

**Telegram.** Botingizga istalgan xabar yozing, keyin `.venv/bin/python notify.py --chat-id` chat ID'ni ko'rsatadi. Ulanganini `.venv/bin/python notify.py --test` bilan tekshirasiz.

## Qo'lda ishga tushirish

```bash
.venv/bin/python sync.py --all          # eClass'dan yangilash + matn + indeks + AI + eslatmalar
.venv/bin/python sync.py --course 2539  # bitta kurs (ID dashboard manzilida: /course/2539)
.venv/bin/python sync.py --all --no-ai --no-notify   # AI va Telegram'siz, tez tekshirish
.venv/bin/python analyze.py --plan      # AI ga nima yuborilishini ko'rish (API chaqirilmaydi)
.venv/bin/python ask.py "limit nima?"   # terminaldan savol berish
.venv/bin/python app.py                 # dashboard: http://127.0.0.1:5050
```

Dashboard'dagi "oxirgi sinxronlash" tugmasi ham sinxronlashni fonda ishga tushiradi. Bir vaqtda faqat bitta sinxronlash ishlaydi.
Bosh sahifaning pastidagi **"Sinxronlash tarixi"** oxirgi 10 ta urinishni ko'rsatadi: qachon, kim boshlagan (tugma, avtomatik yoki terminal), natija va xato bo'lsa, uning sababi. Sichqonchani qatorga olib borsangiz, texnik tafsilot chiqadi.

## Avtomatik ishga tushirish (launchd)

```bash
./deploy/install.sh      # o'rnatish yoki yangilash (kod o'zgargandan keyin ham)
./deploy/uninstall.sh    # to'xtatish va olib tashlash (ma'lumotlar o'chmaydi)
```

| Agent | Nima qiladi |
|---|---|
| `com.eclass.sync` | har 3 soatda `sync.py --all` |
| `com.eclass.notify` | har 30 daqiqada muddat eslatmalari (24 soat va 3 soat qolganda); eClass'ga so'rov yubormaydi |
| `com.eclass.web` | dashboard doim yoqiq, yiqilsa qayta ko'tariladi |

Kod yangilangandan keyin dashboard'ni qayta ishga tushirish: `launchctl kickstart -k gui/$(id -u)/com.eclass.web`.
Mac uxlab qolgan paytdagi ishga tushishlar uyg'ongandan keyin bittaga birlashadi. Loglar `data/logs/` papkasida.

## Testlarni ishga tushirish

**Unit testlar (pytest).** Tez (1 soniyadan kam), internetsiz ishlaydi, haqiqiy bazaga va `.env` dagi kalitlarga tegmaydi:

```bash
.venv/bin/pip install -r requirements-dev.txt   # bir marta (pytest, Playwright)
.venv/bin/pytest                               # hammasi
.venv/bin/pytest tests/test_ask.py -v          # bitta fayl, har bir test nomi bilan
```

| Fayl | Nimani tekshiradi |
|---|---|
| `tests/test_parsers.py` | eClass sahifalarini o'qish: kurslar, haftalar, faoliyatlar, topshiriq jadvali, fayl nomlari (`tests/fixtures/` dagi namuna HTML) |
| `tests/test_db.py` | upsert'lar, sha256 bo'yicha dublikat fayllarni oldini olish, bir xil nomli fayllar ustma-ust yozilmasligi |
| `tests/test_ask.py` | `/api/ask` soxta AI bilan: ko'pi bilan 3 manba, topilmasa manba yo'q, suhbat xotirasi, xato xabarlari |
| `tests/test_answers.py` | formulalarni tiklash (`\frac`, `\to` …), javobdan `found`/`cited` so'zlarini olib tashlash, manba raqamlari |
| `tests/test_search.py` | qidiruv indeksi va natijalar (soxta embedding bilan) |
| `tests/test_reliability.py` | eClass xato turlari, sinxronlash tarixi, parolning logga tushmasligi, AI vaqt chegarasi va zaxira modellar, tarjimalar |
| `tests/test_security.py` | Host/Origin himoyasi, xavfsizlik sarlavhalari, path traversal, SQL/FTS injection, XSS |

**Brauzer testlari (Playwright).** Ishlab turgan dashboard kerak; `chat` va `translate` haqiqiy AI'dan foydalanadi:

```bash
.venv/bin/playwright install chromium    # bir marta
.venv/bin/python tests/e2e.py smoke      # barcha sahifalar, 3 til, 1400px va 390px
.venv/bin/python tests/e2e.py chat       # Shahzod AI (AI tokenlari sarflanadi)
.venv/bin/python tests/e2e.py all
E2E_BASE=http://127.0.0.1:5099 .venv/bin/python tests/e2e.py smoke   # boshqa portdagi nusxani tekshirish
```

## Muammolarni bartaraf etish

| Belgi | Nima qilish kerak |
|---|---|
| "eClass'ga kirib bo'lmadi" (login) | Brauzerda https://eclass.inha.ac.kr ga shu login/parol bilan kiring. Parol o'zgargan bo'lsa, `.env` dagi `ECLASS_PASS` ni yangilang. Qiymatda bo'sh joy yoki qo'shtirnoq qolib ketmaganini tekshiring. Keyin `.venv/bin/python sync.py --course <ID> --no-ai --no-notify` bilan tekshiring |
| "login va parol .env faylida yozilmagan" | `.env` loyiha papkasida turibdimi (`ls -la .env`), `ECLASS_USER=` va `ECLASS_PASS=` qatorlari to'ldirilganmi |
| "sessiyasi tugadi va qayta kirib bo'lmadi" | Odatda eClass vaqtincha nosoz. Keyinroq qayta urinib ko'ring; takrorlansa, parolni tekshiring |
| "eClass juda sekin javob berdi" / "ulanib bo'lmadi" | Internetni va saytning brauzerda ochilishini tekshiring. Sayt sekin bo'lsa, `.env` ga `ECLASS_TIMEOUT=120` yozing. Bitta kurs sahifasi javob bermasa, qolgan kurslar baribir sinxronlanadi |
| "sahifasi kutilgan ko'rinishda emas" | eClass dizayni o'zgargan bo'lishi mumkin. `data/logs/sync.log` ning oxirini ko'ring va sahifa manzilini dasturchiga yuboring |
| Chatda "AI juda sekin javob bermoqda" | Birozdan keyin qayta so'rang. Tez-tez takrorlansa, `.env` ga tezroq model qo'ying (`AI_PROVIDER=gemini:gemini-3.5-flash-lite,...`) yoki `AI_FALLBACK` bilan zaxira model qo'shing |
| "Bugungi bepul AI limiti tugadi" | Ertaga qayta urinib ko'ring yoki `AI_PROVIDER` / `AI_FALLBACK` ga boshqa provayder qo'shing |
| Formula o'rnida `$...$` matni ko'rinadi | Model noto'g'ri LaTeX yozgan: formula bo'sh qolmasligi uchun asl matn ko'rsatiladi. Brauzer konsolida sababi ogohlantirish sifatida yoziladi |
| Dashboard ochilmaydi | `launchctl print gui/$(id -u)/com.eclass.web \| grep state` va `data/logs/web.log`. 5050-port band bo'lsa: `lsof -i :5050` |
| Telegram xabari kelmaydi | `.venv/bin/python notify.py --test`. `TELEGRAM_CHAT_ID` ni `notify.py --chat-id` bilan qayta aniqlang |

Loglar: `data/logs/sync.log` (sinxronlash), `data/logs/web.log` (dashboard), `data/logs/notify.log` (eslatmalar). Ularda parol va kalitlar hech qachon yozilmaydi.

## Xavfsizlik va maxfiylik

- **eClass login va paroli** faqat `.env` da turadi va faqat https://eclass.inha.ac.kr ga yuboriladi. Ular log, xato xabari yoki sinxronlash tarixiga tushmaydi (testlar bilan tekshiriladi).
- **Dashboard** faqat `127.0.0.1` da tinglaydi, debug o'chiq. Boshqa `Host` nomi bilan kelgan so'rovlar rad etiladi (DNS rebinding'dan himoya). `/api/*` ga POST so'rovlari faqat dashboard'ning o'zidan (Origin/Referer tekshiruvi) va faqat JSON ko'rinishida qabul qilinadi (CSRF'dan himoya). Sahifani boshqa sayt iframe ichiga ololmaydi.
- **Fayllar** `/file/<id>` orqali, faqat ID bilan beriladi va faqat `data/files/` ichidan (path traversal'dan himoya).
- **Bazaga so'rovlar** parametrli: foydalanuvchi matni SQL'ga qo'shilmaydi. Sahifada chiqadigan hamma matn escape qilinadi.
- **`data/` papkasi** (baza, fayllar, loglar) faqat shu macOS foydalanuvchisiga ochiq (`chmod 700`), `.gitignore` da turadi va git tarixiga hech qachon tushmagan.
- **AI provayderlariga (Groq va ulangan bo'lsa Gemini) yuboriladi:** materiallar matni (PDF/PPTX/DOCX, OCR, video transkriptlari, topshiriq shartlari), chatdagi savollar, suhbatning oxirgi bir necha xabari va topilgan parchalar, tarjima uchun o'quv to'plamlari. **Gemini API'ning bepul tarifida Google yuborilgan ma'lumotlardan o'z mahsulotlarini yaxshilash uchun foydalanadi.** Buni istamasangiz, `GEMINI_API_KEY` ni olib tashlang. Maxfiy material uchun `AI_PROVIDER=ollama` bilan lokal model ishlating.
- **Qidiruv indeksi (embedding)** kompyuterning o'zida hisoblanadi (`BAAI/bge-small-en-v1.5`) va tashqariga chiqmaydi.
- **Telegram'ga** faqat eslatma matnlari ketadi: kurs nomi, material yoki topshiriq nomi, muddat va baho.

## Tuzilma

- `eclass/`: modullar
  - `config.py`: yo'llar, eClass manzili, vaqt chegaralari va boshqa sozlamalar bitta joyda
  - `auth.py` (eClass'ga kirish, xato turlari), `courses.py`, `activities.py`, `files.py`: eClass sahifalarini o'qish va fayllarni yuklash
  - `db.py`: SQLite sxemasi va yozish funksiyalari (`sync_runs`: sinxronlash tarixi)
  - `extract.py`, `videos.py`, `study.py`, `chapters.py`: matn, transkriptlar, o'quv to'plamlari, darslik boblari
  - `ai.py` (provayderlar zanjiri), `latex.py` (formulalarni tiklash), `rag.py` (chat: qidiruv va javob), `search.py` (Cmd+K)
  - `notify.py`, `telegram.py`: eslatmalar; `i18n.py`: foydalanuvchiga ko'rinadigan barcha matnlar (uz/en/ru)
- `sync.py`, `analyze.py`, `ask.py`, `notify.py`: buyruq qatori vositalari
- `app.py`, `templates/`, `static/`: dashboard. KaTeX va shriftlar lokal, internetsiz ham ishlaydi
- `tests/`: pytest testlari, namuna HTML (`fixtures/`) va Playwright tekshiruvlari (`e2e.py`)
- `deploy/`: launchd shablonlari va o'rnatish skriptlari
- `data/`: baza, yuklangan fayllar, loglar va modellar (git'da yo'q)
