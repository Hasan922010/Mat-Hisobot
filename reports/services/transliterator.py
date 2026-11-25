"""Lotin -> Kirill fonetik konvertori (O'zbek alifbosi)."""

import re

_DIGRAPHS = [
    ("O'", "Ў"), ("O‘", "Ў"), ("O’", "Ў"), ("O`", "Ў"),
    ("o'", "ў"), ("o‘", "ў"), ("o’", "ў"), ("o`", "ў"),
    ("G'", "Ғ"), ("G‘", "Ғ"), ("G’", "Ғ"), ("G`", "Ғ"),
    ("g'", "ғ"), ("g‘", "ғ"), ("g’", "ғ"), ("g`", "ғ"),
    ("SH", "Ш"), ("Sh", "Ш"), ("sh", "ш"),
    ("CH", "Ч"), ("Ch", "Ч"), ("ch", "ч"),
    ("YO", "Ё"), ("Yo", "Ё"), ("yo", "ё"),
    ("YU", "Ю"), ("Yu", "Ю"), ("yu", "ю"),
    ("YA", "Я"), ("Ya", "Я"), ("ya", "я"),
    ("YE", "Е"), ("Ye", "Е"), ("ye", "е"),
    ("TS", "Ц"), ("Ts", "Ц"), ("ts", "ц"),
]

_SINGLES = str.maketrans({
    "A": "А", "a": "а",
    "B": "Б", "b": "б",
    "D": "Д", "d": "д",
    "E": "Е", "e": "е",
    "F": "Ф", "f": "ф",
    "G": "Г", "g": "г",
    "H": "Ҳ", "h": "ҳ",
    "I": "И", "i": "и",
    "J": "Ж", "j": "ж",
    "K": "К", "k": "к",
    "L": "Л", "l": "л",
    "M": "М", "m": "м",
    "N": "Н", "n": "н",
    "O": "О", "o": "о",
    "P": "П", "p": "п",
    "Q": "Қ", "q": "қ",
    "R": "Р", "r": "р",
    "S": "С", "s": "с",
    "T": "Т", "t": "т",
    "U": "У", "u": "у",
    "V": "В", "v": "в",
    "X": "Х", "x": "х",
    "Y": "Й", "y": "й",
    "Z": "З", "z": "з",
    "'": "ъ", "’": "ъ", "‘": "ъ", "`": "ъ",
})

_WORD_START_E = re.compile(r"\bE")
_WORD_START_e = re.compile(r"\be")


def latin_to_cyrillic(text: str) -> str:
    """Lotin yozuvidagi o'zbekcha matnni Kirill alifbosiga o'giradi."""
    if not text:
        return ""
    result = str(text)
    for lat, cyr in _DIGRAPHS:
        result = result.replace(lat, cyr)
    result = _WORD_START_E.sub("Э", result)
    result = _WORD_START_e.sub("э", result)
    return result.translate(_SINGLES)
