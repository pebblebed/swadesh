#!/usr/bin/env python3
"""Brahmic-romanization G2P -> broad IPA, for the romanized Indic lists.

Kannada is in proper ISO-15919 (ā/ī macrons, ṭ/ḍ/ṇ retroflex dots, c=/t͡ʃ/) -> a
reliable transliteration. Hindi is a LOOSE ad-hoc romanization (`pani`, `danth`,
`ankh`) with no length/retroflex marks and ambiguous aspirate digraphs -> broad and
noisy (low confidence). Aspirates -> Cʰ, retroflexes ṭ/ḍ/ṇ/ṣ/ḷ/ṛ -> ʈ/ɖ/ɳ/ʂ/ɭ/ɽ,
c/j -> ʧ/ʤ (folded to tie-bars by ipa_features), doubled letters -> geminate.

Run `python scripts/brahmic_g2p.py` for the self-tests.
"""
import re
import unicodedata

_SEP = re.compile(r"[,;/]")
_GEM = r"([kɡʈɖɳʂɭɽʃʧʤʋjbdhlmnprstf])\1"


def _kan_word(w):
    s = unicodedata.normalize("NFC", w)
    for d, r in [("kh", "kʰ"), ("gh", "ɡʰ"), ("ch", "ʧʰ"), ("jh", "ʤʰ"), ("ṭh", "ʈʰ"),
                 ("ḍh", "ɖʰ"), ("th", "tʰ"), ("dh", "dʰ"), ("ph", "pʰ"), ("bh", "bʰ")]:
        s = s.replace(d, r)
    for d, r in [("ṭ", "ʈ"), ("ḍ", "ɖ"), ("ṇ", "ɳ"), ("ṣ", "ʂ"), ("ḷ", "ɭ"), ("ṛ", "ɽ"),
                 ("ś", "ʃ"), ("ñ", "ɲ"), ("ṅ", "ŋ"), ("c", "ʧ"), ("j", "ʤ"), ("ṃ", "m"),
                 ("ḥ", "h"), ("r̲", "ɾ"), ("v", "ʋ"), ("y", "j")]:
        s = s.replace(d, r)
    for d, r in [("ā", "aː"), ("ī", "iː"), ("ū", "uː"), ("ē", "eː"), ("ō", "oː")]:
        s = s.replace(d, r)
    return re.sub(_GEM, r"\1ː", s).replace("g", "ɡ")


def _hin_word(w):
    s = w
    for d, r in [("chh", "ʧʰ"), ("kh", "kʰ"), ("gh", "ɡʰ"), ("jh", "ʤʰ"), ("th", "tʰ"),
                 ("dh", "dʰ"), ("ph", "f"), ("bh", "bʰ"), ("sh", "ʃ"), ("ch", "ʧ")]:
        s = s.replace(d, r)
    for d, r in [("aa", "\x01"), ("ee", "iː"), ("ii", "iː"), ("oo", "uː"), ("uu", "uː")]:
        s = s.replace(d, r)                            # \x01 = long-a placeholder
    s = (s.replace("c", "ʧ").replace("j", "ʤ").replace("w", "ʋ").replace("v", "ʋ")
         .replace("y", "j").replace("a", "ə").replace("\x01", "aː"))
    return re.sub(_GEM, r"\1ː", s).replace("g", "ɡ")


_LANG = {"kan": _kan_word, "hin": _hin_word}
_CONF = {"kan": "high", "hin": "low"}


def to_ipa(text, lang):
    fn = _LANG[lang]
    text = unicodedata.normalize("NFC", text).strip().lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    keep = lambda c: c.isalpha() or unicodedata.combining(c) or c in " '"
    out = []
    for alt in _SEP.split(text):
        alt = "".join(c if keep(c) else " " for c in alt).strip()
        ipa = " ".join(fn(x) for x in alt.split() if x)
        if ipa and ipa not in out:
            out.append(ipa)
    return ", ".join(out), _CONF[lang]


_TESTS = {
    "kan": [("nīr", "niːr"), ("kiccu", "kiʧːu"), ("kaṇ", "kaɳ"), ("eraḍu", "eraɖu"),
            ("daṭṭa", "daʈːa"), ("nāy", "naːj"), ("cukke", "ʧukːe")],
    "hin": [("pani", "pəni"), ("aag", "aːɡ"), ("do", "do"), ("kutta", "kutːə")],
}


def selftest():
    fails = 0
    for lang, cases in _TESTS.items():
        for src, want in cases:
            got = unicodedata.normalize("NFC", _LANG[lang](src))
            if got != unicodedata.normalize("NFC", want):
                fails += 1
                print(f"FAIL {lang} {src!r}: got {got!r} want {want!r}")
    n = sum(len(v) for v in _TESTS.values())
    print(f"brahmic_g2p self-test: {n - fails}/{n} passed")
    return fails


if __name__ == "__main__":
    import sys
    sys.exit(1 if selftest() else 0)
