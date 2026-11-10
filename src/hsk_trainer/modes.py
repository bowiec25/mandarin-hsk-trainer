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
