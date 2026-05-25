#!/usr/bin/env python3
"""Mayan G2P: ALMG-style orthography -> broad IPA (Achi, Ch'orti', Chuj, Kaqchikel,
Jakalteko, Q'eqchi', Mam, Poqomam, K'iche').

One coherent ruleset for the family. Broad phonemic: x->ʃ, j->x, tz->t͡s, ch->t͡ʃ,
y->j (glide), q/q' uvular; the apostrophe is glottalization -- EJECTIVE after a
consonant (rendered with the ejective modifier ʼ, which ipa_features reads as such)
and a GLOTTAL STOP ʔ after a vowel / word-initially; b' is the implosive ɓ. Long
vowels are written doubled (aa->aː). NB: our raw Mayan data has the '\' corruption
standing in for the apostrophe (kek `tx\\i\\` = tx'i'), so we restore it first.

Affricates emitted as ʦ/ʧ (folded to tie-bars by ipa_features). Run
`python scripts/mayan_g2p.py` for the self-test.
"""
import re
import unicodedata

_SEP = re.compile(r"[,;/]")
_VOWELS = "aeiouäï"


def _word(w):
    s = w.replace("\\", "'").replace("·", "ː").replace("7", "ʔ")
    s = s.replace("b'", "ɓ")                       # implosive (before generic ' handling)
    s = s.replace("tz", "ʦ").replace("ch", "ʧ").replace("tx", "ʧ")
    s = s.replace("x", "ʃ").replace("j", "x")      # x->ʃ first, then orthographic j->/x/
    s = s.replace("y", "j").replace("qu", "k")
    # apostrophe: ejective after a consonant, glottal stop after a vowel / initially
    out = []
    for i, c in enumerate(s):
        if c == "'":
            prev = s[i - 1] if i else ""
            out.append("ʔ" if (not prev or prev in _VOWELS or prev == "ː") else "ʼ")
        else:
            out.append(c)
    s = "".join(out)
    for v in "aeiou":
        s = s.replace(v + v, v + "ː")              # long vowels
    return s.replace("ä", "ə").replace("ï", "ɨ")


def to_ipa(text):
    """Mayan orthographic cell -> broad IPA. Returns (ipa, confidence='medium')."""
    text = unicodedata.normalize("NFC", text).strip().lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    out = []
    for alt in _SEP.split(text):
        alt = re.sub(r"[^a-zäï'\\·7 ]", " ", alt).strip()
        ipa = " ".join(_word(x) for x in alt.split() if x)
        if ipa and ipa not in out:
            out.append(ipa)
    return ", ".join(out), "medium"


_TESTS = [
    ("tz'i'", "ʦʼiʔ"),     # dog (K'iche')
    ("ja'", "xaʔ"),        # water
    ("che'", "ʧeʔ"),       # tree
    ("ixim", "iʃim"),      # maize
    ("winaq", "winaq"),    # person
    ("b'aq", "ɓaq"),       # bone
    ("kaab'", "kaːɓ"),     # long vowel + implosive
    ("tx\\i\\", "ʧʼiʔ"),   # dog with the '\'-corruption (tx'i'): ejective + glottal
]


def selftest():
    fails = 0
    for src, want in _TESTS:
        got = unicodedata.normalize("NFC", _word(src))
        if got != unicodedata.normalize("NFC", want):
            fails += 1
            print(f"FAIL {src!r}: got {got!r} want {want!r}")
    print(f"mayan_g2p self-test: {len(_TESTS) - fails}/{len(_TESTS)} passed")
    return fails


if __name__ == "__main__":
    import sys
    sys.exit(1 if selftest() else 0)
