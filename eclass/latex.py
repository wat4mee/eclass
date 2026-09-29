"""Repair LaTeX that JSON decoding turned into control characters.

Models write formulas inside JSON strings. When they forget to double a backslash, commands that start
with a JSON escape letter decode silently instead of failing: \\frac becomes a form feed + "rac",
\\to / \\times / \\text a tab + "o" / "imes" / "ext", \\beta / \\begin a backspace, \\right / \\rho a carriage
return and \\neq / \\nabla a newline. KaTeX then shows a broken formula, or the chat drops it.
"""
import re

# A form feed or backspace never belongs in an answer: it is always the start of \f... or \b....
_ALWAYS = {"\x0c": "\\f", "\x08": "\\b"}

# Tabs and carriage returns are repaired only in front of a known command name, so real ones survive.
_TAB = re.compile(r"\t(?=(?:o|imes|ext|extbf|extit|extrm|heta|au|an|anh|frac|ilde|op|riangle|herefore|binom)"
                  r"(?![A-Za-z]))")
_CR = re.compile(r"\r(?=(?:ight|ightarrow|ho|angle|brace|ceil|floor|Vert|vert)(?![A-Za-z]))")

# A newline is a normal paragraph break, so it is repaired only inside a formula.
_NL = re.compile(r"\n(?=(?:eq|abla|u|ot|otin|eg|exists|leq|geq|mid|parallel|subseteq|supseteq|rightarrow|"
                 r"leftarrow|sim|cong)(?![A-Za-z]))")
_MATH = re.compile(r"\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$(?:[^$\n]|\n(?!\n))+?\$")


def repair(text: str) -> str:
    """Undo JSON-escape damage to LaTeX commands; text without formulas comes back unchanged."""
    if not text:
        return text
    for char, command in _ALWAYS.items():
        text = text.replace(char, command)
    text = _TAB.sub(r"\\t", text)
    text = _CR.sub(r"\\r", text)
    return _MATH.sub(lambda m: _NL.sub(r"\\n", m.group(0)), text)


# Added to every prompt that asks for formulas inside a JSON reply.
JSON_RULE = ("The reply is JSON, so double every LaTeX backslash inside the strings, exactly as JSON requires: "
             "write \"$\\\\frac{a}{b}$\" and \"$x \\\\to 0$\", never a single backslash.")
