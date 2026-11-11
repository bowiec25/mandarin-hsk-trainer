"""The 6 HSK quiz modes, as config (not if-branches)."""

from quizkit.modes import Mode

HSK_MODES: dict[str, Mode] = {
    m.name: m
    for m in [
        Mode(name="char", show=["hanzi"], skill="recognise"),
        Mode(name="char_pinyin", show=["hanzi", "pinyin"], skill="recognise"),
        Mode(name="char_sentence", show=["hanzi", "sentence"], skill="recognise"),
        Mode(
            name="full",
            show=["hanzi", "pinyin", "sentence", "sentence_pinyin"],
            skill="recognise",
        ),
        # Translate a whole sentence; the answer is its English (ADR 0012).
        Mode(
            name="translate",
            show=["sentence"],
            answer_from="sentence",
            skill="sentence",
        ),
        Mode(
            name="translate_pinyin",
            show=["sentence", "sentence_pinyin"],
            answer_from="sentence",
            skill="sentence",
        ),
    ]
}

# How each mode is named on the web page: what you see, and what you type. The terminal
# keeps the short names (`--mode translate`).
MODE_LABELS: dict[str, str] = {
    "char": "Words: the character",
    "char_pinyin": "Words: character + pinyin",
    "char_sentence": "Words: character + example sentence",
    "full": "Words: character, pinyin + example sentence",
    "translate": "Sentences: translate",
    "translate_pinyin": "Sentences: translate, with pinyin",
}


def mode_hint(name: str) -> str:
    """What you'll type in this mode, in one line."""
    if HSK_MODES[name].answer_from == "sentence":
        return "You'll type what the whole sentence means in English."
    return "You'll type the word's meaning in English (any sentence is a hint)."
