# eClass Companion

INHA University in Tashkent eClass tizimi uchun shaxsiy yordamchi. U quyidagilarni qiladi:

- kurs materiallari, topshiriqlar va baholarni avtomatik yuklab oladi;
- har bir material uchun AI yordamida qisqa mazmun, kartalar va test tayyorlaydi;
- "Shahzod AI" chatida materiallar bo'yicha savollarga manbasi bilan javob beradi;
- muddatlar va yangiliklar haqida Telegram'ga eslatma yuboradi;
- hammasini lokal dashboard'da ko'rsatadi: http://127.0.0.1:5050 (o'zbek, ingliz va rus tillarida).

## O'rnatish

Python 3.11 yoki undan yangi versiya kerak (macOS).

```bash
cd eclass
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # keyin .env ni to'ldiring
```

`.env` fayli (faqat shu faylda saqlanadi, git'ga tushmaydi):

| O'zgaruvchi | Majburiy | Ma'nosi |
|---|---|---|
| `ECLASS_USER`, `ECLASS_PASS` | ha | eClass login va paroli |
| `AI_PROVIDER` | yo'q | `auto` (sukut bo'yicha, pastga qarang), `groq`, yoki ro'yxat: `gemini,groq:openai/gpt-oss-120b,ollama` |
| `GROQ_API_KEY` | AI uchun | https://console.groq.com dan bepul kalit |
| `GEMINI_API_KEY` | yo'q | https://aistudio.google.com/apikey dan bepul kalit; `GEMINI_MODEL` sukut bo'yicha `gemini-3.5-flash-lite` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | yo'q | yo'q bo'lsa, Telegram eslatmalari jimgina o'tkazib yuboriladi |
| `STUDY_LANGUAGE` | yo'q | o'quv to'plamlari tili: `uz` (sukut), `en`, `ru` |
| `EMBED_THREADS` | yo'q | qidiruv indeksi uchun CPU yadrolari (sukut: 2) |
| `FLASK_DEBUG` | yo'q | `1` bo'lsa Flask debug rejimi yoqiladi (sukut bo'yicha o'chiq) |

**AI zanjiri (`AI_PROVIDER=auto`).** Bepul limitlar tugab qolmasligi uchun provayderlar navbat bilan ishlatiladi. Birining kunlik limiti tugasa, keyingisiga avtomatik o'tiladi:
Groq `gpt-oss-120b` → Groq `qwen3.8-27b` → Groq `gpt-oss-20b` → Gemini (kalit bo'lsa) → Ollama (ishlayotgan bo'lsa).
Groq'da har bir modelning o'z kunlik limiti bor (bepul tarifda kuniga 200 000 token).
Model band bo'lsa (503 yoki daqiqalik limit), zanjir kutmasdan keyingisiga o'tadi.

Faqat Gemini ishlatish uchun (tez va barqaror): `AI_PROVIDER=gemini:gemini-3.5-flash-lite,gemini:gemini-3.5-flash`.

Telegram chat ID'ni topish: botingizga istalgan xabar yozing, keyin `.venv/bin/python notify.py --chat-id` ni ishga tushiring. Ulanganini `.venv/bin/python notify.py --test` bilan tekshirasiz.

## Qo'lda ishga tushirish

```bash
.venv/bin/python sync.py --all          # eClass'dan yangilash + matn + indeks + AI + eslatmalar
.venv/bin/python sync.py --course 2539  # bitta kurs
.venv/bin/python analyze.py --plan      # AI ga nima yuborilishini ko'rish (API chaqirilmaydi)
.venv/bin/python ask.py "limit nima?"   # terminaldan savol berish
.venv/bin/python app.py                 # dashboard: http://127.0.0.1:5050
```

Dashboard'dagi "oxirgi sinxronlash" tugmasini bossangiz ham sinxronlash fonda ishga tushadi. Bir vaqtda faqat bitta sinxronlash ishlaydi.

## Avtomatik ishga tushirish (launchd)

```bash
./deploy/install.sh      # o'rnatish yoki yangilash
./deploy/uninstall.sh    # to'xtatish va olib tashlash (ma'lumotlar o'chmaydi)
```

O'rnatiladigan agentlar:

| Agent | Nima qiladi |
|---|---|
| `com.eclass.sync` | har 3 soatda `sync.py --all` |
| `com.eclass.notify` | har 30 daqiqada muddat eslatmalari (24 soat va 3 soat qolganda); eClass'ga so'rov yubormaydi |
| `com.eclass.web` | dashboard doim yoqiq, yiqilsa qayta ko'tariladi |

Mac uxlab qolgan paytdagi ishga tushishlar uyg'ongandan keyin bittaga birlashadi. Loglar `data/logs/` papkasida saqlanadi.

`notify` agenti topshiriq holatini oxirgi sinxronlashdan oladi. Agar ishni oxirgi sinxronlashdan keyin topshirgan bo'lsangiz, keyingi sinxronlashgacha eslatma baribir kelishi mumkin.

## Maxfiylik: qaysi ma'lumot qayerga ketadi

- **eClass login va paroli** faqat `.env` da turadi va faqat https://eclass.inha.ac.kr ga yuboriladi. Ular hech qayerda logga yoki ekranga chiqmaydi.
- **AI provayderlariga (Groq modellari va ulangan bo'lsa Gemini) quyidagilar yuboriladi:**
  - o'quv materiallaringizning matni (ma'ruza PDF/PPTX/DOCX fayllari, OCR qilingan sahifalar, video transkriptlari, topshiriq shartlari);
  - Shahzod AI'ga bergan savollaringiz, suhbatning oxirgi bir necha xabari va javob uchun topilgan parchalar;
  - tarjima uchun o'quv to'plamlari matni.

  Groq bu ma'lumotlarni o'z shartlari asosida qayta ishlaydi. Maxfiy material bo'lsa, `AI_PROVIDER=ollama` bilan lokal model ishlating.
- **Gemini (Google) ulangan bo'lsa**, zanjir unga yetib kelganda xuddi shu ma'lumotlar Google'ga yuboriladi. **Gemini API'ning bepul tarifida Google yuborilgan ma'lumotlardan o'z mahsulotlarini yaxshilash uchun foydalanadi** (Google narxlar sahifasida "Used to improve our products: Yes" deb ko'rsatilgan). Buni istamasangiz, `GEMINI_API_KEY` ni olib tashlang yoki `AI_PROVIDER` ro'yxatidan `gemini` ni chiqaring.
- **Qidiruv indeksi (embedding)** kompyuterning o'zida hisoblanadi (`BAAI/bge-small-en-v1.5`) va tashqariga chiqmaydi.
- **Telegram'ga** faqat eslatma matnlari yuboriladi: kurs nomi, material yoki topshiriq nomi, muddat va baho.
- **Barcha fayllar va baza** (`data/`) lokal saqlanadi va `.gitignore` da turadi.
- **Dashboard** faqat `127.0.0.1` da tinglaydi, ya'ni boshqa qurilmalardan kirib bo'lmaydi. `/api/*` so'rovlari boshqa saytlardan qabul qilinmaydi.

## Testlarni ishga tushirish

**Unit testlar (pytest).** Tez (1 soniyadan kam), internetsiz ishlaydi, haqiqiy bazaga va `.env` dagi kalitlarga tegmaydi:

```bash
.venv/bin/pip install -r requirements-dev.txt   # bir marta (pytest)
.venv/bin/pytest                               # hammasi
.venv/bin/pytest tests/test_ask.py -v          # bitta fayl, har bir test nomi bilan
```

| Fayl | Nimani tekshiradi |
|---|---|
| `tests/test_parsers.py` | eClass sahifalarini o'qish: kurslar, haftalar, faoliyatlar, topshiriq jadvali, fayl nomlari (`tests/fixtures/` dagi namuna HTML) |
| `tests/test_db.py` | upsert'lar, sha256 bo'yicha dublikat fayllarni oldini olish, bir xil nomli fayllar ustma-ust yozilmasligi |
| `tests/test_ask.py` | `/api/ask` soxta AI bilan: ko'pi bilan 3 manba, topilmasa manba yo'q, suhbat xotirasi, xato xabarlari, Origin/Host himoyasi |
| `tests/test_answers.py` | formulalarni tiklash (`\frac`, `\to` …), javobdan `found`/`cited` so'zlarini olib tashlash, manba raqamlari |
| `tests/test_search.py` | qidiruv indeksi va natijalar (soxta embedding bilan) |

**Brauzer testlari (Playwright).** Ishlab turgan dashboard kerak; `chat` va `translate` haqiqiy AI'dan foydalanadi:

```bash
.venv/bin/playwright install chromium    # bir marta
.venv/bin/python tests/e2e.py smoke      # barcha sahifalar, 3 til, 1400px va 390px
.venv/bin/python tests/e2e.py chat       # Shahzod AI (AI tokenlari sarflanadi)
.venv/bin/python tests/e2e.py all
E2E_BASE=http://127.0.0.1:5099 .venv/bin/python tests/e2e.py smoke   # boshqa portdagi nusxani tekshirish
```

## Tuzilma

- `eclass/`: modullar (auth, courses, activities, files, db, extract, study, rag, notify, telegram, i18n, …)
- `sync.py`, `analyze.py`, `ask.py`, `notify.py`: buyruq qatori vositalari
- `app.py`, `templates/`, `static/`: dashboard. KaTeX va shriftlar lokal, internetsiz ham ishlaydi.
- `deploy/`: launchd shablonlari va o'rnatish skriptlari
- `data/`: baza, yuklangan fayllar, loglar va modellar (git'da yo'q)
