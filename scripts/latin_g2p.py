#!/usr/bin/env python3
"""Per-language G2P for a few non-Romance Latin-script national orthographies that
are tractable enough for a broad rule-based pass: Esperanto, Finnish, German.

Reliability: Esperanto perfect (1:1 phonemic), Finnish high (near-phonemic; long
vowels/consonants doubled), German medium (ch context, st/sp, umlauts, s-voicing;
silent-h and final devoicing not modeled -> broad). Affricates emitted as ʦ/ʧ/ʤ
(folded by ipa_features). Run `python scripts/latin_g2p.py` for the self-tests.
"""
import re
import unicodedata

_SEP = re.compile(r"[,;/]")


# ------------------------------ Esperanto ---------------------------------
def _eo_word(w):
    s = w
    s = (s.replace("ĉ", "ʧ").replace("ĝ", "ʤ").replace("ĥ", "x").replace("ĵ", "ʒ")
         .replace("ŝ", "ʃ").replace("ŭ", "w"))
    s = (s.replace("cx", "ʧ").replace("gx", "ʤ").replace("hx", "x").replace("jx", "ʒ")
         .replace("sx", "ʃ").replace("ux", "w"))     # x-system fallback
    return s.replace("c", "ʦ").replace("g", "ɡ")     # c = /ts/; g = /ɡ/ (h,v,j kept)


# ------------------------------- Finnish ----------------------------------
def _fi_word(w):
    s = w.replace("ä", "æ").replace("ö", "ø").replace("å", "o")
    s = s.replace("ng", "ŋ").replace("nk", "ŋk")
    s = re.sub(r"([bcdfghjklmnpqrstvwxz])\1", r"\1ː", s)   # geminate consonant -> long
    s = re.sub(r"([aeiouæøy])\1", r"\1ː", s)              # long vowel
    return s


# ------------------------------- German -----------------------------------
def _de_word(w):
    s = w
    s = s.replace("tsch", "ʧ").replace("sch", "ʃ")
    s = re.sub(r"^st", "ʃt", s)
    s = re.sub(r"^sp", "ʃp", s)
    s = s.replace("ß", "s").replace("ck", "k").replace("qu", "kv")
    s = s.replace("ei", "ai").replace("eu", "ɔy").replace("äu", "ɔy").replace("au", "au")
    s = re.sub(r"([aou])ch", r"\1x", s).replace("ch", "ç")
    s = s.replace("ä", "ɛ").replace("ö", "ø").replace("ü", "y")
    s = s.replace("v", "f").replace("w", "v").replace("z", "ʦ").replace("ng", "ŋ")
    s = re.sub(r"^s([aeiouɛøy])", r"z\1", s)              # initial s before vowel -> z
    s = re.sub(r"([aeiouɛøy])s([aeiouɛøy])", r"\1z\2", s)  # intervocalic s -> z
    s = s.replace("ss", "s").replace("c", "k").replace("g", "ɡ")
    return s


_LANG = {"epo": _eo_word, "fin": _fi_word, "deu": _de_word}
_CONF = {"epo": "high", "fin": "high", "deu": "medium"}


def to_ipa(text, lang):
    fn = _LANG[lang]
    text = unicodedata.normalize("NFC", text).strip().lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    out = []
    for alt in _SEP.split(text):
        alt = re.sub(r"[^a-zà-ÿĉĝĥĵŝŭ' ]", " ", alt).strip()
        ipa = " ".join(fn(x) for x in alt.split() if x)
        if ipa and ipa not in out:
            out.append(ipa)
    return ", ".join(out), _CONF[lang]


_TESTS = {
    "epo": [("ĉielo", "ʧielo"), ("hundo", "hundo"), ("akvo", "akvo"),
            ("ĝardeno", "ʤardeno"), ("cento", "ʦento")],
    "fin": [("kala", "kala"), ("tuuli", "tuːli"), ("kukka", "kukːa"),
            ("yö", "yø"), ("käsi", "kæsi")],
    "deu": [("hund", "hund"), ("wasser", "vaser"), ("zunge", "ʦuŋe"),
            ("auge", "auɡe"), ("ich", "iç"), ("feuer", "fɔyer"), ("schön", "ʃøn")],
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
    print(f"latin_g2p self-test: {n - fails}/{n} passed")
    return fails


if __name__ == "__main__":
    import sys
    sys.exit(1 if selftest() else 0)
