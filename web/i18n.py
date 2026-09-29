"""Texts of the hosted site (uz / en / ru). Language logic and shared texts come from eclass/i18n.py."""
from eclass import i18n as base

LANGS = base.LANGS
DEFAULT = base.DEFAULT

S = {
    # chrome
    "web.tagline": {"uz": "Kurslar, muddatlar va baholar bitta joyda, AI yordamchi bilan.",
                    "en": "Your courses, deadlines and grades in one place, with an AI study assistant.",
                    "ru": "Курсы, сроки и оценки в одном месте, с ИИ-помощником."},
    "web.disclaimer": {"uz": "Norasmiy talaba loyihasi, INHA University bilan bog'liq emas.",
                       "en": "Unofficial student project, not affiliated with INHA University.",
                       "ru": "Неофициальный студенческий проект, не связан с INHA University."},
    "web.nav.home": {"uz": "Bosh sahifa", "en": "Home", "ru": "Главная"},
    "web.nav.account": {"uz": "Hisob", "en": "Account", "ru": "Аккаунт"},
    "web.nav.privacy": {"uz": "Maxfiylik", "en": "Privacy", "ru": "Конфиденциальность"},
    "web.nav.logout": {"uz": "Chiqish", "en": "Sign out", "ru": "Выйти"},
    "web.nav.theme": {"uz": "Mavzuni almashtirish", "en": "Toggle theme", "ru": "Сменить тему"},
    # sign-in
    "web.login.title": {"uz": "Kirish", "en": "Sign in", "ru": "Вход"},
    "web.login.lead": {"uz": "eClass login va parolingiz bilan kiring.",
                       "en": "Sign in with your eClass username and password.",
                       "ru": "Войдите с логином и паролем от eClass."},
    "web.login.username": {"uz": "eClass login", "en": "eClass username", "ru": "Логин eClass"},
    "web.login.password": {"uz": "Parol", "en": "Password", "ru": "Пароль"},
    "web.login.submit": {"uz": "Kirish", "en": "Sign in", "ru": "Войти"},
    "web.login.how": {"uz": "Parolingiz faqat eClass'ga kirishni tekshirish uchun ishlatiladi va saqlanmaydi.",
                      "en": "Your password is only used to check your sign-in with eClass. It is not stored.",
                      "ru": "Пароль нужен только для проверки входа в eClass и не сохраняется."},
    "web.login.failed": {"uz": "Kirib bo'lmadi. eClass login va parolingizni tekshiring.",
                         "en": "Sign-in failed. Check your eClass username and password.",
                         "ru": "Не удалось войти. Проверьте логин и пароль от eClass."},
    "web.login.unreachable": {"uz": "eClass hozir javob bermayapti. Bir necha daqiqadan keyin qayta urinib ko'ring.",
                              "en": "eClass is not responding right now. Try again in a few minutes.",
                              "ru": "eClass сейчас не отвечает. Попробуйте через несколько минут."},
    "web.login.missing": {"uz": "Login va parolni kiriting.", "en": "Enter your username and password.",
                          "ru": "Введите логин и пароль."},
    "web.login.too_many": {"uz": "Urinishlar juda ko'p. Birozdan keyin qayta urinib ko'ring.",
                           "en": "Too many attempts. Wait a little and try again.",
                           "ru": "Слишком много попыток. Подождите немного и попробуйте снова."},
    "web.logged_out": {"uz": "Tizimdan chiqdingiz.", "en": "You are signed out.", "ru": "Вы вышли из аккаунта."},
    "web.login.hero": {"uz": "Butun semestr,<br><em>bir qarashda.</em>", "en": "Your semester,<br><em>at a glance.</em>",
                       "ru": "Весь семестр —<br><em>одним взглядом.</em>"},
    "web.login.point.deadlines": {"uz": "Muddatlar jonli sanoq bilan", "en": "Deadlines with a live countdown",
                                  "ru": "Сроки с живым обратным отсчётом"},
    "web.login.point.grades": {"uz": "Baholar va o'rtacha ball", "en": "Grades and your average",
                               "ru": "Оценки и средний балл"},
    "web.ask.welcome": {"uz": "Kurs materiallaringiz bo'yicha istalgan savolni bering.",
                        "en": "Ask anything about your course materials.",
                        "ru": "Задайте любой вопрос по материалам ваших курсов."},
    "web.login.point.ai": {"uz": "Materiallaringizni biladigan AI yordamchi",
                           "en": "An AI assistant that knows your materials",
                           "ru": "ИИ-помощник, который знает ваши материалы"},
    # home (filled in by the sync milestone)
    "web.home.hello": {"uz": "Salom, {name}!", "en": "Hello, {name}!", "ru": "Здравствуйте, {name}!"},
    "web.home.soon": {"uz": "Kurslaringiz birinchi sinxronlashdan keyin shu yerda paydo bo'ladi.",
                      "en": "Your courses will appear here after the first sync.",
                      "ru": "Ваши курсы появятся здесь после первой синхронизации."},
    # account
    "web.account.title": {"uz": "Hisob va ma'lumotlar", "en": "Account and data", "ru": "Аккаунт и данные"},
    "web.account.username": {"uz": "eClass login", "en": "eClass username", "ru": "Логин eClass"},
    "web.account.joined": {"uz": "Ro'yxatdan o'tgan", "en": "Joined", "ru": "Зарегистрирован"},
    "web.account.last_login": {"uz": "Oxirgi kirish", "en": "Last sign-in", "ru": "Последний вход"},
    "web.account.stored": {"uz": "Siz haqingizda nima saqlanadi", "en": "What we store about you",
                           "ru": "Что мы храним о вас"},
    "web.account.stored_text": {
        "uz": "eClass loginingiz, kurslaringiz ro'yxati, topshiriqlar muddatlari va baholaringiz, o'rganilgan deb "
              "belgilagan materiallaringiz va sinxronlash tarixi. Parolingiz saqlanmaydi.",
        "en": "Your eClass username, your course list, assignment deadlines and grades, the materials you marked as "
              "studied, and your sync history. Your password is not stored.",
        "ru": "Ваш логин eClass, список курсов, сроки заданий и оценки, отметки об изученных материалах и история "
              "синхронизации. Пароль не хранится."},
    "web.delete.title": {"uz": "Ulanishni uzish va ma'lumotlarimni o'chirish", "en": "Disconnect & delete my data",
                         "ru": "Отключить и удалить мои данные"},
    "web.delete.text": {
        "uz": "Hisobingiz va siz bilan bog'liq barcha ma'lumotlar darhol va butunlay o'chiriladi. Buni qaytarib "
              "bo'lmaydi. eClass'dagi hisobingizda hech narsa o'zgarmaydi.",
        "en": "Your account and all data linked to you are deleted immediately and permanently. This cannot be "
              "undone. Nothing changes in your eClass account.",
        "ru": "Ваш аккаунт и все связанные с вами данные удаляются сразу и навсегда. Это нельзя отменить. "
              "В вашем аккаунте eClass ничего не меняется."},
    "web.delete.confirm": {"uz": "Tushundim, hammasini o'chirish", "en": "I understand, delete everything",
                           "ru": "Понимаю, удалить всё"},
    "web.delete.need_confirm": {"uz": "O'chirish uchun belgini qo'ying.", "en": "Tick the box to confirm.",
                                "ru": "Отметьте флажок, чтобы подтвердить."},
    "web.delete.done": {"uz": "Hisobingiz va ma'lumotlaringiz o'chirildi.", "en": "Your account and data are deleted.",
                        "ru": "Ваш аккаунт и данные удалены."},
    # errors
    "web.err.csrf": {"uz": "Sahifa eskirgan. Uni yangilab, qayta urinib ko'ring.",
                     "en": "This page has expired. Reload it and try again.",
                     "ru": "Страница устарела. Обновите её и попробуйте снова."},
    "web.err.429.title": {"uz": "Juda ko'p so'rov", "en": "Too many requests", "ru": "Слишком много запросов"},
    "web.err.500.text": {"uz": "Xatolik yuz berdi va qayd etildi. Birozdan keyin qayta urinib ko'ring.",
                         "en": "Something went wrong and it was logged. Please try again in a moment.",
                         "ru": "Произошла ошибка, она записана. Попробуйте чуть позже."},
    # privacy page
    "web.privacy.title": {"uz": "Maxfiylik: nimani saqlaymiz va nima uchun", "en": "Privacy: what we store and why",
                          "ru": "Конфиденциальность: что мы храним и зачем"},
    "web.privacy.intro": {
        "uz": "{app} — norasmiy talaba loyihasi. U eClass'dagi ma'lumotlaringizni qulay ko'rinishda ko'rsatish uchun "
              "sizning nomingizdan eClass'ga kiradi. Quyida hammasi oddiy tilda yozilgan.",
        "en": "{app} is an unofficial student project. To show your eClass data in a friendlier way, it signs in to "
              "eClass on your behalf. Here is everything, in plain language.",
        "ru": "{app} — неофициальный студенческий проект. Чтобы показывать ваши данные из eClass в удобном виде, "
              "он входит в eClass от вашего имени. Ниже всё описано простыми словами."},
    "web.privacy.password.h": {"uz": "Parolingiz", "en": "Your password", "ru": "Ваш пароль"},
    "web.privacy.password": {
        "uz": "Kirishda parolingiz to'g'riligini tekshirish uchun bir marta eClass'ga yuboriladi. Shundan keyin u "
              "hech qayerda saqlanmaydi, loglarga ham yozilmaydi.",
        "en": "When you sign in, your password is sent once to eClass to check it. After that it is not kept "
              "anywhere, not even in logs.",
        "ru": "При входе пароль один раз отправляется в eClass для проверки. После этого он нигде не хранится, "
              "даже в логах."},
    "web.privacy.session.h": {"uz": "eClass sessiyasi", "en": "Your eClass session", "ru": "Сессия eClass"},
    "web.privacy.session": {
        "uz": "Kirgandan keyin eClass bergan sessiya kaliti (cookie) shifrlangan holda ko'pi bilan 2 soat saqlanadi: "
              "shu vaqt ichida sayt siz uchun materiallarni yangilay oladi. Chiqsangiz yoki muddati tugasa, u "
              "o'chiriladi.",
        "en": "After you sign in, the session cookie eClass gives us is kept encrypted for at most 2 hours, so the "
              "site can refresh your materials while you use it. It is deleted when you sign out or when it expires.",
        "ru": "После входа cookie сессии eClass хранится в зашифрованном виде не больше 2 часов, чтобы сайт мог "
              "обновлять ваши материалы. Он удаляется, когда вы выходите или когда истекает срок."},
    "web.privacy.data.h": {"uz": "Nimani saqlaymiz", "en": "What we store", "ru": "Что мы храним"},
    "web.privacy.data": {
        "uz": "eClass loginingiz; kurslaringiz; topshiriqlar muddatlari, topshirish holati va baholaringiz; "
              "o'rganilgan deb belgilagan materiallaringiz; sinxronlash tarixi; AI'ga kunlik savollaringiz soni. "
              "Kurs materiallari (fayl nomlari, havolalar va matni) shu kursdagi talabalar uchun bitta nusxada "
              "saqlanadi. Fayllarning o'zi saqlanmaydi: ochganingizda ular eClass'dan siz uchun olinadi.",
        "en": "Your eClass username; your courses; assignment deadlines, submission status and grades; materials "
              "you marked as studied; your sync history; and how many AI questions you asked each day. Course "
              "materials (file names, links and their text) are stored once per course and shared by the students "
              "enrolled in it. Files themselves are not stored: when you open one, it is fetched from eClass for you.",
        "ru": "Ваш логин eClass; ваши курсы; сроки заданий, статус сдачи и оценки; материалы, отмеченные как "
              "изученные; история синхронизации; число вопросов к ИИ за день. Материалы курса (названия файлов, "
              "ссылки и текст) хранятся в одном экземпляре на курс и доступны его студентам. Сами файлы не "
              "хранятся: при открытии они загружаются из eClass для вас."},
    "web.privacy.protect.h": {"uz": "Qanday himoyalanadi", "en": "How it is protected", "ru": "Как это защищено"},
    "web.privacy.protect": {
        "uz": "Saqlanadigan maxfiy qiymatlar (eClass sessiyasi) Fernet (AES) bilan shifrlanadi. Shifr kaliti faqat "
              "server sozlamalarida turadi: bazada ham, kodda ham yo'q. Sayt faqat HTTPS orqali ishlaydi, kirish "
              "urinishlari cheklangan, loglarda parol va cookie'lar yashiriladi.",
        "en": "Stored secrets (your eClass session) are encrypted with Fernet (AES). The encryption key lives only in "
              "the server settings, never in the database or the code. The site only works over HTTPS, sign-in "
              "attempts are rate-limited, and passwords and cookies are masked in logs.",
        "ru": "Хранимые секреты (сессия eClass) зашифрованы Fernet (AES). Ключ шифрования есть только в настройках "
              "сервера — ни в базе данных, ни в коде. Сайт работает только по HTTPS, число попыток входа "
              "ограничено, пароли и cookie в логах скрываются."},
    "web.privacy.ai.h": {"uz": "AI yordamchi", "en": "The AI assistant", "ru": "ИИ-помощник"},
    "web.privacy.ai": {
        "uz": "AI yordamchiga bergan savollaringiz va kurs materiallaridan olingan parchalar javob yozish uchun "
              "Google Gemini'ga yuboriladi. Gemini API'ning bepul tarifida Google bu ma'lumotlardan o'z "
              "mahsulotlarini yaxshilash uchun foydalanishi mumkin, shuning uchun chatga shaxsiy ma'lumot yozmang.",
        "en": "Questions you ask the AI assistant, together with passages from your course materials, are sent to "
              "Google Gemini to write the answer. On the free tier of the Gemini API, Google may use this data to "
              "improve its products, so do not type personal information into the chat.",
        "ru": "Вопросы к ИИ-помощнику вместе с отрывками из материалов курса отправляются в Google Gemini для "
              "ответа. На бесплатном тарифе Gemini API Google может использовать эти данные для улучшения своих "
              "продуктов, поэтому не пишите в чат личную информацию."},
    "web.privacy.who.h": {"uz": "Kim ko'radi", "en": "Who can see it", "ru": "Кто это видит"},
    "web.privacy.who": {
        "uz": "Shaxsiy ma'lumotlaringizni (baholar, topshiriqlar, sinxronlash tarixi) faqat siz ko'rasiz. Kurs "
              "materiallarini faqat o'sha kursga yozilgan talabalar ko'radi. Ma'lumotlar sotilmaydi va reklama "
              "uchun ishlatilmaydi.",
        "en": "Only you see your personal data (grades, assignments, sync history). Course materials are visible "
              "only to students enrolled in that course. Nothing is sold or used for advertising.",
        "ru": "Ваши личные данные (оценки, задания, история синхронизации) видите только вы. Материалы курса видят "
              "только студенты этого курса. Ничего не продаётся и не используется для рекламы."},
    "web.privacy.delete.h": {"uz": "Ma'lumotlarni o'chirish", "en": "Deleting your data", "ru": "Удаление данных"},
    "web.privacy.delete": {
        "uz": "Hisob sahifasidagi «Ulanishni uzish va ma'lumotlarimni o'chirish» tugmasi hisobingizni va siz bilan "
              "bog'liq hamma narsani darhol o'chiradi. Boshqa hech kim foydalanmayotgan kurs materiallari ham "
              "o'chiriladi.",
        "en": "The \"Disconnect & delete my data\" button on the Account page deletes your account and everything "
              "linked to you right away. Course materials that no one else uses are deleted too.",
        "ru": "Кнопка «Отключить и удалить мои данные» на странице аккаунта сразу удаляет ваш аккаунт и всё, что "
              "с ним связано. Материалы курсов, которыми больше никто не пользуется, тоже удаляются."},
    "web.privacy.official.h": {"uz": "Norasmiy loyiha", "en": "An unofficial project", "ru": "Неофициальный проект"},
    "web.privacy.official": {
        "uz": "INHA University va eClass bu saytga javobgar emas va uni boshqarmaydi.",
        "en": "INHA University and eClass are not responsible for this site and do not run it.",
        "ru": "INHA University и eClass не отвечают за этот сайт и не управляют им."},
    # sync status (home page banner)
    "web.sync.running": {"uz": "eClass'dan ma'lumotlaringiz olinmoqda… Birinchi marta bir necha daqiqa oladi.",
                         "en": "Getting your data from eClass… The first time takes a few minutes.",
                         "ru": "Загружаем ваши данные из eClass… В первый раз это займёт несколько минут."},
    "web.sync.last": {"uz": "Oxirgi yangilanish: {when}", "en": "Last updated {when}", "ru": "Обновлено {when}"},
    "web.sync.now": {"uz": "Hozir yangilash", "en": "Refresh now", "ru": "Обновить сейчас"},
    "web.sync.failed": {"uz": "Oxirgi yangilash bajarilmadi: {reason}", "en": "The last refresh failed: {reason}",
                        "ru": "Последнее обновление не удалось: {reason}"},
    "web.sync.expired": {"uz": "eClass sessiyasi tugadi. Yangilash va fayllarni ochish uchun parolingizni qayta kiriting.",
                         "en": "Your eClass session has ended. Enter your password again to refresh and open files.",
                         "ru": "Сессия eClass закончилась. Введите пароль снова, чтобы обновлять данные и открывать файлы."},
    "web.sync.reconnect": {"uz": "Qayta ulash", "en": "Reconnect", "ru": "Переподключить"},
    "web.sync.err.other": {"uz": "kutilmagan xato. Birozdan keyin qayta urinib ko'ring.",
                           "en": "an unexpected error. Try again in a while.",
                           "ru": "непредвиденная ошибка. Попробуйте позже."},
    "web.home.empty": {"uz": "Hali kurslar yo'q.", "en": "No courses yet.", "ru": "Курсов пока нет."},
    "web.reconnect.title": {"uz": "eClass'ga qayta ulanish", "en": "Reconnect to eClass",
                            "ru": "Переподключение к eClass"},
    "web.reconnect.lead": {"uz": "Ma'lumotlarni yangilash va fayllarni ochish uchun eClass parolingizni kiriting.",
                           "en": "Enter your eClass password to refresh your data and open files.",
                           "ru": "Введите пароль от eClass, чтобы обновить данные и открывать файлы."},
    "web.ask.limit": {"uz": "Bugungi {n} ta savol limiti tugadi. Ertaga yana so'rang.",
                      "en": "You have used today's {n} questions. Ask again tomorrow.",
                      "ru": "Лимит на сегодня ({n} вопросов) исчерпан. Спросите снова завтра."},
}


def t(lang: str, key: str, **kw) -> str:
    entry = S.get(key) or base.S[key]
    text = entry.get(lang) or entry[DEFAULT]
    return text.format(**kw) if kw else text


def pick(requested: str | None, accept_languages=None) -> str:
    """?lang= or cookie first, then the browser's preference, then Uzbek."""
    if requested in LANGS:
        return requested
    if accept_languages is not None:
        return accept_languages.best_match(list(LANGS)) or DEFAULT
    return DEFAULT
