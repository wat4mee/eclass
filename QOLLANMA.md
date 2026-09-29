# eClass Companion: o'rnatish va foydalanish qo'llanmasi

Bu qo'llanma INHA University in Tashkent talabalari uchun. Dastur sizning eClass kurslaringizdagi materiallar, topshiriqlar va baholarni kompyuteringizga yuklab oladi. Keyin ularni qulay sahifada ko'rsatadi, har bir materialga AI yordamida qisqa mazmun, kartalar va test tayyorlaydi. "Shahzod AI" chatida esa ma'ruzalar bo'yicha savol berishingiz mumkin.

Hammasi **sizning kompyuteringizda** ishlaydi. Login va parolingiz boshqa hech kimga yuborilmaydi (faqat eClass saytiga).

---

## Kerak bo'ladi

- **Mac** (macOS; Apple Silicon M1–M4 da sinovdan o'tgan). Windows hozircha qo'llab-quvvatlanmaydi.
- Kompyuterda **1 GB atrofida bo'sh joy**.
- **eClass login va parolingiz**.
- **Bepul Gemini API kaliti** (quyida qanday olish yozilgan). Kredit karta kerak emas.
- 20–30 daqiqa vaqt (birinchi marta).

Buyruqlar **Terminal** dasturida yoziladi: `Cmd + Space` ni bosing, "Terminal" deb yozing, Enter. Har bir buyruqni nusxalab, Terminal'ga qo'ying va Enter bosing.

---

## 1-qadam. Python o'rnatish

Terminal'da tekshiring:

```bash
python3 --version
```

`Python 3.11` yoki undan katta raqam chiqsa, 2-qadamga o'ting. `3.9` chiqsa yoki buyruq topilmasa, https://www.python.org/downloads/ saytidan eng yangi Python'ni yuklab, oddiy dastur kabi o'rnating (Mac'ning o'zidagi 3.9 versiyasi eski). Keyin Terminal'ni yopib, qayta oching va tekshiruvni takrorlang.

Agar "install command line developer tools" degan oyna chiqsa, **Install** ni bosing va tugashini kuting.

## 2-qadam. Dasturni kompyuterga joylash

Do'stingiz bergan `eclass.zip` faylini oching (ustiga ikki marta bosing). Chiqqan `eclass` papkasini **uy papkangizga** (Finder'da uy belgisi, `/Users/<ismingiz>`) ko'chiring.

GitHub'ga taklif qilingan bo'lsangiz, ZIP o'rniga shunday olasiz:
```bash
cd ~ && git clone https://github.com/muhammadshahzod/eclass.git
```

## 3-qadam. Kerakli kutubxonalarni o'rnatish

```bash
cd ~/eclass
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Bu bir necha daqiqa oladi. Oxirida qizil `ERROR` yozuvi bo'lmasa, hammasi joyida.

## 4-qadam. Bepul Gemini kalitini olish

1. https://aistudio.google.com/apikey saytiga Google akkauntingiz bilan kiring.
2. **Create API key** ni bosing va chiqqan uzun kalitni nusxalang (`AIza...` bilan boshlanadi).

Kalit **faqat sizniki**: uni hech kimga bermang. Bepul limit kalitga bog'langan, boshqalar ishlatsa, sizning limitingiz tugaydi.

## 5-qadam. Login va kalitni yozish

```bash
cp .env.example .env
chmod 600 .env
open -e .env
```

TextEdit'da `.env` fayli ochiladi. Quyidagi qatorlarni to'ldiring (`=` dan keyin, bo'sh joy va qo'shtirnoqsiz):

```
ECLASS_USER=sizning_eclass_loginingiz
ECLASS_PASS=sizning_eclass_parolingiz
AI_PROVIDER=gemini:gemini-3.5-flash-lite,gemini:gemini-3.5-flash
GEMINI_API_KEY=AIza...sizning_kalitingiz
```

Qolgan qatorlarga tegmang. Saqlang (`Cmd + S`) va yoping.

> `.env` faylida parolingiz turadi. Bu faylni hech kimga yubormang va papkani boshqalarga bermoqchi bo'lsangiz, uni qo'shib yubormang.

## 6-qadam. Birinchi sinxronlash

```bash
.venv/bin/python sync.py --all
```

Dastur eClass'ga kiradi, kurslaringiz va materiallarni yuklab oladi, matnni o'qiydi va qidiruv indeksini tuzadi. Birinchi marta bu **10–30 daqiqa** olishi mumkin (materiallar soniga qarab). Oxirida `=== Report ===` va `errors: 0` chiqsa, tayyor.

- `login failed` yoki "eClass'ga kirib bo'lmadi" chiqsa, login va parolni `.env` da tekshiring (5-qadam).
- AI o'quv to'plamlari bepul limit tufayli **bir necha kun davomida asta-sekin** tayyorlanadi. Bu normal holat: har sinxronlashda bir qismi qo'shiladi.

## 7-qadam. Dashboard'ni ochish

```bash
.venv/bin/python app.py
```

Brauzerda oching: **http://127.0.0.1:5050**. To'xtatish uchun Terminal'da `Ctrl + C` bosing.

## 8-qadam. Doim o'zi ishlab tursin (tavsiya etiladi)

Har safar Terminal ochmaslik uchun:

```bash
bash deploy/install.sh
```

Shundan keyin:
- dashboard kompyuter yoqilganda o'zi ishga tushadi: http://127.0.0.1:5050 ni brauzerda saqlab qo'ying;
- har 3 soatda eClass'dan yangiliklar avtomatik olinadi;
- har 30 daqiqada muddatlar tekshiriladi (Telegram ulangan bo'lsa).

To'xtatish: `bash deploy/uninstall.sh` (yuklangan ma'lumotlar o'chmaydi).

## 9-qadam (ixtiyoriy). Telegram eslatmalari

Yangi material, yangi baho va muddatga 24 yoki 3 soat qolganda Telegram'ga xabar kelishini xohlasangiz:

1. Telegram'da **@BotFather** ga yozing, `/newbot` buyrug'ini bering, botga nom bering. U bergan **token** ni nusxalang.
2. O'z botingizni oching va unga istalgan xabar yozing (masalan "salom").
3. Token'ni `.env` dagi `TELEGRAM_BOT_TOKEN=` qatoriga yozing va saqlang.
4. Terminal'da chat ID'ni toping va uni `TELEGRAM_CHAT_ID=` qatoriga yozing:
   ```bash
   .venv/bin/python notify.py --chat-id
   ```
5. Tekshirish: `.venv/bin/python notify.py --test`. Telegram'ga "eClass Companion ulandi" xabari kelishi kerak.

---

## Qanday foydalaniladi

| Qayerda | Nima bor |
|---|---|
| **Bosh sahifa** | Salomlashuv va yaqin muddat sanog'i. **"Bugun nima qilish kerak"** blokida yaqin topshiriqlar, o'rganilmagan material va bitta maslahat bor. Pastda topshiriqlar, baholar, yangi materiallar, kurslar va **"Sinxronlash tarixi"** |
| **Kurs sahifasi** | Materiallar haftalar bo'yicha. Joriy hafta belgilangan. Fayl nomini bossangiz, asl fayl ochiladi |
| **"O'rganish" tugmasi** | Qisqa mazmun, asosiy tushunchalar, aylanadigan kartalar (`←` `→`, `Space`) va 5 savollik test. O'qib bo'lgach **"O'rganildi"** deb belgilang |
| **Darsliklar ("Boblar")** | Katta kitob boblarga bo'linadi. Kerakli bobda **"Tayyorlash"** ni bosing: to'plam bir necha daqiqada tayyor bo'ladi va saqlanib qoladi |
| **Shahzod AI** (yuqoridagi menyu) | Ma'ruzalar bo'yicha savol bering, masalan "Limit nima?" yoki "Unga misol ber". Yuqoridagi tugmalar bilan bitta kursni tanlash mumkin. Javobdagi `[1]` raqamini bossangiz, manba (fayl va bet) ochiladi. Materiallarda yo'q narsani to'qib chiqarmaydi |
| **Qidiruv** | `Cmd + K` (yoki `/`): kurslar, fayllar, topshiriqlar va to'plamlar bo'yicha tez qidiruv |
| **Baholar** | Kurslar bo'yicha to'plangan ball va foizlar |
| **Yuqori o'ng burchak** | 🌐 til (o'zbek, ingliz, rus), ☀️/🌙 mavzu. "… oldin" tugmasi eClass'dan hozir yangilaydi |

---

## Yangilash (yangi versiya chiqqanda)

Yangi ZIP'ni oching va undagi fayllarni eski `eclass` papkasi ustiga ko'chiring. **`.env` fayli va `data` papkasini o'chirmang**: ularda login va yuklangan hamma narsa turadi. GitHub orqali olgan bo'lsangiz, `git pull` yetarli. Keyin:

```bash
cd ~/eclass
.venv/bin/pip install -r requirements.txt
bash deploy/install.sh
```

## Butunlay o'chirish

```bash
cd ~/eclass && bash deploy/uninstall.sh
```

Keyin `eclass` papkasini Savatga tashlang. Gemini kalitini https://aistudio.google.com/apikey da o'chirib qo'yish mumkin.

## Maxfiylik: bilib qo'ying

- eClass login va parolingiz faqat sizning kompyuteringizdagi `.env` faylida turadi va faqat eClass saytiga yuboriladi.
- Yuklangan fayllar, baholar va baza faqat kompyuteringizda (`data` papkasida) saqlanadi.
- AI ishlashi uchun **material matnlari va chatdagi savollaringiz Google Gemini'ga yuboriladi.** Gemini'ning bepul tarifida Google bu ma'lumotlardan o'z mahsulotlarini yaxshilash uchun foydalanadi. Shaxsiy yoki maxfiy narsalarni chatga yozmang.
- Dashboard faqat sizning kompyuteringizda ochiladi (`127.0.0.1`). Bir tarmoqdagi boshqa odamlar unga kira olmaydi.

## Tez-tez uchraydigan muammolar

| Muammo | Yechim |
|---|---|
| `command not found: python3` yoki versiya 3.9 | 1-qadam: python.org'dan Python o'rnating, Terminal'ni qayta oching |
| `pip install` xato bilan tugadi | `.venv/bin/pip install -U pip` ni bajaring, keyin 3-qadamni takrorlang |
| "eClass'ga kirib bo'lmadi" | Brauzerda eclass.inha.ac.kr ga o'sha login bilan kirib ko'ring. `.env` dagi qiymatlarda bo'sh joy yoki qo'shtirnoq bo'lmasin |
| "Bugungi bepul AI limiti tugadi" | Ertaga o'zi davom etadi. Kalitni boshqalar bilan bo'lishmang |
| "AI juda sekin javob bermoqda" | Bir daqiqadan keyin qayta so'rang |
| Sahifa ochilmaydi (http://127.0.0.1:5050) | 7-qadamdagi buyruq ishlayaptimi yoki 8-qadam bajarilganmi, tekshiring. Qayta ishga tushirish: `bash deploy/install.sh` |
| Formula o'rnida `$...$` matn | AI formulani xato yozgan. Savolni qayta bering |

Batafsil texnik ma'lumot: `README.md` ("Muammolarni bartaraf etish" bo'limi). Loglar `data/logs/` papkasida, ularda parol yozilmaydi.

---

## Dasturni do'stingizga berish (egasi uchun)

Papkani o'zini **bermang**: unda `.env` (parolingiz, kalitlaringiz) va `data` (baholaringiz) bor. Buning o'rniga faqat kodni ZIP qiling:

```bash
cd ~/all\ codes/eclass
git archive --format=zip --prefix=eclass/ -o ~/Desktop/eclass.zip HEAD
```

`~/Desktop/eclass.zip` (taxminan 1 MB) ichida faqat kod bor: `.env`, `data` va baza kirmaydi. Shu faylni va bu qo'llanmani yuboring. Yoki GitHub'da repo → **Settings → Collaborators** orqali do'stingizni taklif qiling (repo yopiq).
