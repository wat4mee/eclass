"""Dashboard translations: Uzbek (default), English, Russian."""

LANGS = {"uz": "O'zbekcha", "en": "English", "ru": "Русский"}
DEFAULT = "uz"
AI_LANGUAGE = {"uz": "Uzbek (Latin script)", "en": "English", "ru": "Russian"}

MONTHS = {
    "uz": ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"],
    "ru": ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
           "ноября", "декабря"],
}
MONTHS_SHORT = {
    "uz": ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "ru": ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"],
}
WEEKDAYS = {
    "uz": ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "ru": ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"],
}

# word forms after a number: uz has one form, en singular/plural, ru one/few/many
PLURALS = {
    "material": {"uz": ("material",), "en": ("material", "materials"), "ru": ("материал", "материала", "материалов")},
    "pack": {"uz": ("to'plam",), "en": ("pack", "packs"), "ru": ("набор", "набора", "наборов")},
    "study_pack": {"uz": ("o'quv to'plami",), "en": ("study pack", "study packs"),
                   "ru": ("учебный набор", "учебных набора", "учебных наборов")},
    "assignment": {"uz": ("topshiriq",), "en": ("assignment", "assignments"), "ru": ("задание", "задания", "заданий")},
    "course": {"uz": ("ta kurs",), "en": ("course", "courses"), "ru": ("курс", "курса", "курсов")},
}

S = {
    # chrome
    "nav.home": {"uz": "Bosh sahifa", "en": "Home", "ru": "Главная"},
    "nav.grades": {"uz": "Baholar", "en": "Grades", "ru": "Оценки"},
    "nav.ai": {"uz": "Shahzod AI", "en": "Shahzod AI", "ru": "Shahzod AI"},
    "sync.title": {"uz": "Oxirgi sinxronlash", "en": "Last sync", "ru": "Последняя синхронизация"},
    "sync.never": {"uz": "hali yo'q", "en": "never", "ru": "ещё не было"},
    "theme.toggle": {"uz": "Mavzuni almashtirish", "en": "Toggle theme", "ru": "Сменить тему"},
    "lang.label": {"uz": "Til", "en": "Language", "ru": "Язык"},
    "ago.now": {"uz": "hozirgina", "en": "just now", "ru": "только что"},
    # assignment states
    "state.overdue": {"uz": "Muddati o'tgan", "en": "Overdue", "ru": "Просрочено"},
    "state.soon": {"uz": "Yaqin", "en": "Due soon", "ru": "Скоро срок"},
    "state.upcoming": {"uz": "Kutilmoqda", "en": "Upcoming", "ru": "Предстоит"},
    "state.nodate": {"uz": "Muddatsiz", "en": "No deadline", "ru": "Без срока"},
    "state.done": {"uz": "Topshirilgan", "en": "Submitted", "ru": "Сдано"},
    "status.graded": {"uz": "Baholangan", "en": "Graded", "ru": "Оценено"},
    "status.not graded": {"uz": "Baholanmagan", "en": "Not graded", "ru": "Не оценено"},
    # home
    "greet.morning": {"uz": "Xayrli tong", "en": "Good morning", "ru": "Доброе утро"},
    "greet.day": {"uz": "Xayrli kun", "en": "Good afternoon", "ru": "Добрый день"},
    "greet.evening": {"uz": "Xayrli kech", "en": "Good evening", "ru": "Добрый вечер"},
    "greet.night": {"uz": "Xayrli tun", "en": "Good night", "ru": "Доброй ночи"},
    "home.tagline": {"uz": "o'qishga tayyormisiz?", "en": "ready to study?", "ru": "готовы к учёбе?"},
    "home.pending": {"uz": "<b>{n} ta</b> topshiriq kutmoqda", "en": "<b>{n}</b> {word} waiting",
                     "ru": "Ждут сдачи: <b>{n}</b>"},
    "home.all_done": {"uz": "Barcha topshiriqlar topshirilgan", "en": "All assignments submitted",
                      "ru": "Все задания сданы"},
    "home.packs": {"uz": "<b>{n} ta</b> o'quv to'plami tayyor.", "en": "<b>{n}</b> {word} ready.",
                   "ru": "Готово: <b>{n}</b> {word}."},
    "home.next_due": {"uz": "Keyingi muddat", "en": "Next deadline", "ru": "Ближайший срок"},
    "home.until": {"uz": "{date} gacha", "en": "until {date}", "ru": "до {date}"},
    "unit.days": {"uz": "kun", "en": "days", "ru": "дн."},
    "unit.hours": {"uz": "soat", "en": "hours", "ru": "ч"},
    "home.no_deadlines": {"uz": "Yaqin muddatlar yo'q", "en": "No upcoming deadlines", "ru": "Ближайших сроков нет"},
    "home.no_deadlines_hint": {"uz": "Yangi topshiriq chiqsa, shu yerda sanoq boshlanadi.",
                               "en": "When a new assignment appears, the countdown starts here.",
                               "ru": "Когда появится новое задание, здесь начнётся отсчёт."},
    "stat.pending": {"uz": "Topshirilmagan", "en": "Not submitted", "ru": "Не сдано"},
    "stat.avg": {"uz": "O'rtacha baho", "en": "Average grade", "ru": "Средний балл"},
    "stat.materials": {"uz": "Materiallar", "en": "Materials", "ru": "Материалы"},
    "stat.packs": {"uz": "O'quv to'plamlari", "en": "Study packs", "ru": "Учебные наборы"},
    "home.assignments": {"uz": "Topshiriqlar", "en": "Assignments", "ru": "Задания"},
    "home.unsubmitted": {"uz": "topshirilmaganlar", "en": "not submitted", "ru": "не сданы"},
    "home.all": {"uz": "Hammasi", "en": "All", "ru": "Все"},
    "home.new_materials": {"uz": "Yangi materiallar", "en": "New materials", "ru": "Новые материалы"},
    "home.everything_submitted": {"uz": "Hammasi topshirilgan", "en": "Everything is submitted", "ru": "Всё сдано"},
    "home.no_grades": {"uz": "Hali baho qo'yilmagan", "en": "No grades yet", "ru": "Оценок пока нет"},
    "home.courses": {"uz": "Kurslar", "en": "Courses", "ru": "Курсы"},
    "home.study_ready": {"uz": "O'quv to'plami tayyor materiallar", "en": "Materials with a ready study pack",
                         "ru": "Материалы с готовым учебным набором"},
    "study.open": {"uz": "O'rganish", "en": "Study", "ru": "Изучить"},
    # course
    "type.ubfile": {"uz": "Fayl", "en": "File", "ru": "Файл"},
    "type.folder": {"uz": "Papka", "en": "Folder", "ru": "Папка"},
    "type.url": {"uz": "Video", "en": "Video", "ru": "Видео"},
    "type.assign": {"uz": "Topshiriq", "en": "Assignment", "ru": "Задание"},
    "type.ubboard": {"uz": "Doska", "en": "Board", "ru": "Доска"},
    "course.ask": {"uz": "Shahzod AI'dan so'rash", "en": "Ask Shahzod AI", "ru": "Спросить Shahzod AI"},
    "course.open_eclass": {"uz": "eClass'da ochish", "en": "Open in eClass", "ru": "Открыть в eClass"},
    "week.n": {"uz": "{n}-hafta", "en": "Week {n}", "ru": "Неделя {n}"},
    "week.general": {"uz": "Umumiy", "en": "General", "ru": "Общее"},
    "week.current": {"uz": "Joriy hafta", "en": "This week", "ru": "Текущая неделя"},
    "assign.due": {"uz": "Muddat: {date}", "en": "Due: {date}", "ru": "Срок: {date}"},
    "assign.left": {"uz": "{t} qoldi", "en": "{t} left", "ru": "осталось {t}"},
    "assign.no_due": {"uz": "Muddatsiz", "en": "No deadline", "ru": "Без срока"},
    "assign.grade": {"uz": "Baho: {g}", "en": "Grade: {g}", "ru": "Оценка: {g}"},
    # study
    "study.suffix": {"uz": "o'rganish", "en": "study", "ru": "изучение"},
    "study.tab.summary": {"uz": "Mazmun", "en": "Summary", "ru": "Конспект"},
    "study.tab.cards": {"uz": "Kartalar", "en": "Cards", "ru": "Карточки"},
    "study.tab.quiz": {"uz": "Test", "en": "Quiz", "ru": "Тест"},
    "study.summary": {"uz": "Qisqa mazmun", "en": "Summary", "ru": "Краткое содержание"},
    "study.question_n": {"uz": "Savol · {n}", "en": "Question · {n}", "ru": "Вопрос · {n}"},
    "study.flip_hint": {"uz": "Javobni ko'rish uchun bosing", "en": "Tap to see the answer",
                        "ru": "Нажмите, чтобы увидеть ответ"},
    "study.answer": {"uz": "Javob", "en": "Answer", "ru": "Ответ"},
    "study.prev": {"uz": "Oldingi", "en": "Previous", "ru": "Назад"},
    "study.next": {"uz": "Keyingi", "en": "Next", "ru": "Далее"},
    "study.keys": {"uz": "<kbd>←</kbd> <kbd>→</kbd> almashtirish · <kbd>Space</kbd> aylantirish · telefonda suring",
                   "en": "<kbd>←</kbd> <kbd>→</kbd> switch · <kbd>Space</kbd> flip · swipe on a phone",
                   "ru": "<kbd>←</kbd> <kbd>→</kbd> листать · <kbd>Space</kbd> перевернуть · на телефоне — свайп"},
    "study.next_question": {"uz": "Keyingi savol", "en": "Next question", "ru": "Следующий вопрос"},
    "study.restart": {"uz": "Qaytadan", "en": "Try again", "ru": "Заново"},
    "study.translating": {"uz": "O'zbekchaga tarjima qilinmoqda…", "en": "Translating into English…",
                          "ru": "Переводим на русский…"},
    "study.translating_hint": {"uz": "Hozircha asl nusxa ko'rsatilmoqda.", "en": "Showing the original meanwhile.",
                               "ru": "Пока показан оригинал."},
    # grades
    "grades.title": {"uz": "Baholar va topshiriqlar", "en": "Grades and assignments", "ru": "Оценки и задания"},
    "grades.eyebrow": {"uz": "Semestr natijalari", "en": "Semester results", "ru": "Итоги семестра"},
    "grades.average": {"uz": "o'rtacha", "en": "average", "ru": "средний"},
    "grades.graded": {"uz": "baholangan", "en": "graded", "ru": "оценено"},
    "grades.submitted": {"uz": "topshirilgan", "en": "submitted", "ru": "сдано"},
    "grades.total": {"uz": "jami topshiriq", "en": "assignments in total", "ru": "всего заданий"},
    "grades.not_graded": {"uz": "Baholanmagan", "en": "Not graded", "ru": "Не оценено"},
    "col.course": {"uz": "Kurs", "en": "Course", "ru": "Курс"},
    "col.assignment": {"uz": "Topshiriq", "en": "Assignment", "ru": "Задание"},
    "col.due": {"uz": "Muddat", "en": "Due", "ru": "Срок"},
    "col.status": {"uz": "Holat", "en": "Status", "ru": "Статус"},
    "col.grade": {"uz": "Baho", "en": "Grade", "ru": "Оценка"},
    # Shahzod AI
    "ask.eyebrow": {"uz": "Sizning AI yordamchingiz", "en": "Your AI study assistant", "ru": "Ваш AI-ассистент"},
    "ask.subtitle": {"uz": "Javoblar faqat ma'ruza va darsliklardan olinadi, manbasi sahifasi bilan ko'rsatiladi.",
                     "en": "Answers come only from your lectures and textbooks, with the exact source page.",
                     "ru": "Ответы только из ваших лекций и учебников — с указанием страницы источника."},
    "ask.all_courses": {"uz": "Barcha kurslar", "en": "All courses", "ru": "Все курсы"},
    "ask.welcome": {"uz": "Istalgan mavzuni so'rang. Masalan:", "en": "Ask about any topic. For example:",
                    "ru": "Спросите о любой теме. Например:"},
    "ask.placeholder": {"uz": "Savolingizni yozing…", "en": "Type your question…", "ru": "Введите вопрос…"},
    "ask.send": {"uz": "Yuborish", "en": "Send", "ru": "Отправить"},
    "ask.keys": {"uz": "<kbd>Enter</kbd> yuborish · <kbd>Shift</kbd>+<kbd>Enter</kbd> yangi qator",
                 "en": "<kbd>Enter</kbd> send · <kbd>Shift</kbd>+<kbd>Enter</kbd> new line",
                 "ru": "<kbd>Enter</kbd> отправить · <kbd>Shift</kbd>+<kbd>Enter</kbd> новая строка"},
    "ask.not_found": {"uz": "Materiallarda bu haqida ma'lumot topilmadi.",
                      "en": "Your materials don't contain information about this.",
                      "ru": "В ваших материалах нет информации об этом."},
    "err.question": {"uz": "Savol bo'sh yoki juda uzun (1000 belgigacha).",
                     "en": "The question is empty or too long (up to 1000 characters).",
                     "ru": "Вопрос пустой или слишком длинный (до 1000 символов)."},
    "err.ai": {"uz": "AI javob bera olmadi, birozdan keyin qayta urinib ko'ring.",
               "en": "The AI could not answer, please try again in a moment.",
               "ru": "AI не смог ответить, попробуйте чуть позже."},
    "err.ai_quota": {"uz": "Bugungi bepul AI limiti tugadi, ertaga qayta urinib ko'ring.",
                     "en": "Today's free AI quota is used up, please try again tomorrow.",
                     "ru": "Бесплатный лимит AI на сегодня исчерпан, попробуйте завтра."},
    # strings used from JavaScript (sent to the page as one object)
    "js.day_short": {"uz": "kun", "en": "d", "ru": "д"},
    "js.q_of": {"uz": "Savol {i} / {n}", "en": "Question {i} / {n}", "ru": "Вопрос {i} / {n}"},
    "js.correct": {"uz": "{n} to'g'ri", "en": "{n} correct", "ru": "верно: {n}"},
    "js.result": {"uz": "Natija", "en": "Result", "ru": "Результат"},
    "js.perfect": {"uz": "Mukammal! Hammasi to'g'ri 🎉", "en": "Perfect! All correct 🎉", "ru": "Отлично! Всё верно 🎉"},
    "js.good": {"uz": "Yaxshi natija! Yana bir urinib ko'ring.", "en": "Nice result! Give it another try.",
                "ru": "Хороший результат! Попробуйте ещё раз."},
    "js.low": {"uz": "Mazmunni yana bir ko'rib chiqing, keyin qayta urining.",
               "en": "Review the summary once more, then try again.", "ru": "Перечитайте конспект и попробуйте снова."},
    "js.translate_failed": {"uz": "Tarjima qilib bo'lmadi", "en": "Translation failed", "ru": "Не удалось перевести"},
    "js.suggest": {"uz": "{t} nima?", "en": "What is {t}?", "ru": "Что такое {t}?"},
    "js.searching": {"uz": "Materiallar qidirilmoqda…", "en": "Searching your materials…", "ru": "Ищу в материалах…"},
    "js.writing": {"uz": "Javob yozilmoqda…", "en": "Writing the answer…", "ru": "Пишу ответ…"},
    "js.query": {"uz": "Qidiruv", "en": "Search", "ru": "Поиск"},
    "js.page": {"uz": "{n}-bet", "en": "p. {n}", "ru": "стр. {n}"},
    "js.pages": {"uz": "{n}-betlar", "en": "pp. {n}", "ru": "стр. {n}"},
    "js.open_source": {"uz": "Manbani ochish", "en": "Open source", "ru": "Открыть источник"},
    "js.network": {"uz": "Ulanishda muammo bo'ldi.", "en": "There was a connection problem.",
                   "ru": "Проблема с подключением."},
    "js.timeout": {"uz": "Javob kutish vaqti tugadi.", "en": "The answer took too long.", "ru": "Слишком долго нет ответа."},
    "js.retry": {"uz": "Qayta urinish", "en": "Try again", "ru": "Повторить"},
}


def pick(lang):
    return lang if lang in LANGS else DEFAULT


def t(lang, key, **kw):
    entry = S[key]
    text = entry.get(lang) or entry[DEFAULT]
    return text.format(**kw) if kw else text


def plural(lang, n, word):
    forms = PLURALS[word].get(lang) or PLURALS[word][DEFAULT]
    if len(forms) == 1:
        return forms[0]
    if len(forms) == 2:
        return forms[0] if n == 1 else forms[1]
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


def duration(lang, delta):
    minutes = int(delta.total_seconds() // 60)
    days, rem = divmod(minutes, 24 * 60)
    hours, mins = divmod(rem, 60)
    fmt = {
        "uz": ("{d} kun {h} soat", "{h} soat {m} daqiqa", "{m} daqiqa"),
        "en": ("{d}d {h}h", "{h}h {m}m", "{m} min"),
        "ru": ("{d} дн {h} ч", "{h} ч {m} мин", "{m} мин"),
    }[pick(lang)]
    if days:
        return fmt[0].format(d=days, h=hours)
    return fmt[1].format(h=hours, m=mins) if hours else fmt[2].format(m=mins)


def ago(lang, delta):
    minutes = int(delta.total_seconds() // 60)
    fmt = {
        "uz": ("{n} daqiqa oldin", "{n} soat oldin", "{n} kun oldin"),
        "en": ("{n} min ago", "{n} h ago", "{n} d ago"),
        "ru": ("{n} мин назад", "{n} ч назад", "{n} дн назад"),
    }[pick(lang)]
    if minutes < 1:
        return t(lang, "ago.now")
    if minutes < 60:
        return fmt[0].format(n=minutes)
    if minutes < 24 * 60:
        return fmt[1].format(n=minutes // 60)
    return fmt[2].format(n=minutes // (24 * 60))


def short_date(lang, value):
    month = MONTHS_SHORT[pick(lang)][value.month - 1]
    if lang == "en":
        return f"{month} {value.day}, {value:%H:%M}"
    return f"{value.day} {month}, {value:%H:%M}"


def day_range(lang, start, end):
    ms = MONTHS_SHORT[pick(lang)]
    if lang == "en":
        return f"{ms[start.month - 1]} {start.day} – {ms[end.month - 1]} {end.day}"
    return f"{start.day} {ms[start.month - 1]} – {end.day} {ms[end.month - 1]}"


def long_date(lang, value):
    lang = pick(lang)
    weekday, month = WEEKDAYS[lang][value.weekday()], MONTHS[lang][value.month - 1]
    if lang == "en":
        return f"{weekday}, {month} {value.day}"
    return f"{weekday}, {value.day} {month}"


def js_strings(lang):
    return {k[3:]: t(lang, k) for k in S if k.startswith("js.")}
