"""Answer text clean-up: LaTeX damaged by JSON escapes, leaked JSON field names, citation numbering."""
import json

from eclass import ai, latex, rag


def test_json_escapes_inside_latex_are_repaired():
    raw = r'{"a": "$$\frac{f(a+h)-f(a)}{h}$$, $x \to 0$, $a \times b$, $\beta$, $\\left( x \right)$, $a \neq b$"}'
    text = ai.unescape(json.loads(raw))["a"]
    for command in ("\\frac", "\\to", "\\times", "\\beta", "\\left", "\\right", "\\neq"):
        assert command in text
    assert not any(c in text for c in "\x08\x0c\r\t")


def test_correct_latex_and_plain_text_are_unchanged():
    good = "$\\lim_{x \\to 0} \\frac{\\sin x}{x} = 1$"
    assert latex.repair(good) == good
    text = "Birinchi qator.\n\nneq bu so'z emas\n\tkod"
    assert latex.repair(text) == text
    assert latex.repair("$$\nx^2$$") == "$$\nx^2$$"  # a newline that starts a formula stays
    assert latex.repair("") == ""


def test_unescape_handles_nested_values():
    value = ai.unescape({"quiz": [{"q": "bo\\u2018lgan \x0crac{1}{2}"}], "n": 3})
    assert value == {"quiz": [{"q": "bo‘lgan \\frac{1}{2}"}], "n": 3}


def test_field_names_never_reach_the_student():
    assert rag.clean_answer("Limit - bu tushuncha [1], va mos ravishda found=true.") == "Limit - bu tushuncha [1]."
    assert rag.clean_answer("Hosila $f'(x)$ [1]. found kalit so'zi true qilib belgilandi.") == "Hosila $f'(x)$ [1]."
    assert rag.clean_answer('Javob: $x^2$ [2]; "cited": [1, 2]') == "Javob: $x^2$ [2]"
    assert rag.clean_answer("Qadamlar:\n- birinchi\n- ikkinchi (found = false)") == "Qadamlar:\n- birinchi\n- ikkinchi"


def test_normal_text_with_the_same_words_is_kept():
    for text in ("It was found that the limit exists [1].", "Chaqiruv: `obj.method()` [1].",
                 "A standalone function has no class [2]."):
        assert rag.clean_answer(text) == text


def test_citations_renumbered_deduplicated_and_dropped():
    renumber = rag._renumber_citations
    assert renumber("a [3], [6] va b [3][6].", {3: 1, 6: 2}) == "a [1], [2] va b [1], [2]."
    assert renumber("formula [1], [1].", {1: 1}) == "formula [1]."
    assert renumber("qonun keltirilgan [2], [6].", {}) == "qonun keltirilgan."
    assert renumber("$\\[1\\]$ va javob [2].", {2: 1}) == "$\\[1\\]$ va javob [1]."
