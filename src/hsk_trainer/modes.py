"""The 4 HSK quiz modes, as config (not if-branches)."""

from quizkit.modes import Mode

HSK_MODES: dict[str, Mode] = {
    m.name: m
    for m in [
        Mode(name="char", show=["hanzi"]),
        Mode(name="char_pinyin", show=["hanzi", "pinyin"]),
        Mode(name="char_sentence", show=["hanzi", "sentence"]),
        Mode(name="full", show=["hanzi", "pinyin", "sentence", "sentence_pinyin"]),
    ]
}
