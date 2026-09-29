"""Browser checks for the dashboard (needs the app running on 127.0.0.1:5050, or E2E_BASE=http://...).

    .venv/bin/python tests/e2e.py smoke        # every page, 3 languages, desktop + 390 px
    .venv/bin/python tests/e2e.py chat         # Shahzod AI: follow-up question, "no data", formulas
    .venv/bin/python tests/e2e.py translate    # study pack translation into English
    .venv/bin/python tests/e2e.py all
"""
import os
import re
import sys

from playwright.sync_api import sync_playwright

BASE = os.getenv("E2E_BASE", "http://127.0.0.1:5050")
PAGES = ["/", "/grades", "/ask", "/course/2539", "/course/2596", "/study/7", "/does-not-exist"]
failures = []


def check(ok, label):
    print(("  PASS " if ok else "  FAIL ") + label)
    if not ok:
        failures.append(label)


def new_page(browser, width=1400, height=900, lang="uz"):
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
    context.add_cookies([{"name": "lang", "value": lang, "url": BASE}])
    page = context.new_page()
    page.errors = []
    page.on("console", lambda m: m.type == "error" and page.errors.append(m.text))
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    return page


def smoke(browser):
    print("smoke: pages x languages x widths")
    for lang in ("uz", "en", "ru"):
        for width in (1400, 390):
            page = new_page(browser, width, 844 if width == 390 else 900, lang)
            for path in PAGES:
                page.errors.clear()
                resp = page.goto(BASE + path, wait_until="networkidle")
                expected = 404 if path == "/does-not-exist" else 200
                overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
                errors = [e for e in page.errors if "/api/translate" not in e and "404" not in e]
                check(resp.status == expected and overflow <= 1 and not errors,
                      f"{lang} {width}px {path}: status={resp.status} overflow={overflow} console={errors[:2]}")
            page.context.close()


def ask(page, text, timeout=150000):
    before = page.locator(".msg.bot").count()
    page.fill("#question", text)
    page.keyboard.press("Enter")
    bubble = page.locator(".msg.bot").nth(before)
    bubble.locator(".answer, .error").first.wait_for(timeout=timeout)
    return bubble


def chat(browser):
    print("chat: Shahzod AI")
    page = new_page(browser)
    page.goto(BASE + "/ask?course=2539", wait_until="networkidle")
    first = ask(page, "Limit nima?")
    check(first.locator(".answer").count() == 1, f"answer to 'Limit nima?': {first.inner_text()[:160]!r}")
    second = ask(page, "Unga oddiy misol ber")
    text = second.inner_text()
    query = second.locator(".query").inner_text() if second.locator(".query").count() else ""
    check("limit" in query.lower() and "derivative" not in query.lower() and second.locator(".src").count() >= 1,
          f"follow-up stays on limits with sources: query={query!r} answer={text[:200]!r}")
    check(second.locator(".src").count() <= 3, f"at most 3 sources ({second.locator('.src').count()})")
    labels = second.locator(".src-page").all_inner_texts()
    print("    sources:", second.locator(".src-title").all_inner_texts(), labels)
    check(page.locator(".katex").count() > 0 or "$" not in text, "formulas rendered by KaTeX (no raw $...$)")
    third = ask(page, "Toshkent aholisi qancha?")
    check(third.locator(".answer.not-found").count() == 1 and third.locator(".src").count() == 0,
          f"'Toshkent aholisi' -> no data, no sources: {third.inner_text()[:160]!r}")
    check(not page.errors, f"no console errors {page.errors[:2]}")
    page.context.close()


def translate(browser):
    print("translate: study pack -> English")
    page = new_page(browser, lang="en")
    page.goto(BASE + "/study/8", wait_until="networkidle")
    if page.locator("#translating").count():
        page.wait_for_function("!document.getElementById('translating')", timeout=180000)
    summary = page.locator("#summary").inner_text()
    english = len(re.findall(r"\b(the|is|of|and|a|to)\b", summary.lower()))
    check(english >= 5, f"summary is English ({english} common words): {summary[:160]!r}")
    check(not page.errors, f"no console errors {page.errors[:2]}")
    page.context.close()


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, fn in (("smoke", smoke), ("chat", chat), ("translate", translate)):
            if which in (name, "all"):
                fn(browser)
        browser.close()
    print(f"\n{len(failures)} failure(s)")
    sys.exit(1 if failures else 0)
