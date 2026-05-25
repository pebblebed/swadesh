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


# --------- Turkic (Turkish / Gagauz / Balkar) -- shared broad rules ----------
def _tr_word(w):
    s = w.replace("ç", "ʧ").replace("ş", "ʃ").replace("c", "ʤ")
    s = s.replace("ğ", "ː").replace("j", "ʒ").replace("y", "j").replace("ñ", "ŋ")
    s = s.replace("ı", "ɯ").replace("ö", "ø").replace("ü", "y")   # AFTER y->j (ü = vowel /y/)
    return s.replace("g", "ɡ")


# ------------------------------- Albanian ---------------------------------
def _sq_word(w):
    s = w
    s = (s.replace("dh", "ð").replace("th", "θ").replace("sh", "ʃ").replace("zh", "ʒ")
         .replace("xh", "ʤ").replace("gj", "ɟ").replace("nj", "ɲ").replace("rr", "r")
         .replace("ll", "ɫ"))
    s = s.replace("ç", "ʧ").replace("c", "ʦ").replace("x", "ʣ").replace("q", "c")
    return s.replace("ë", "ə").replace("g", "ɡ")


# -------------------------------- Polish ----------------------------------
def _pl_word(w):
    s = w.replace("dż", "ʤ").replace("dź", "ʤ").replace("dz", "ʣ")
    s = s.replace("cz", "ʧ").replace("sz", "ʃ").replace("rz", "ʒ").replace("ch", "x")
    s = s.replace("ż", "ʒ").replace("ź", "ʒ").replace("ś", "ʃ").replace("ć", "ʧ")
    s = s.replace("w", "v").replace("ł", "w")             # w->v BEFORE ł->w
    s = s.replace("c", "ʦ").replace("ń", "ɲ").replace("h", "x")
    s = s.replace("ą", "ɔ").replace("ę", "ɛ").replace("ó", "u").replace("y", "ɨ")
    return s.replace("g", "ɡ")


# ------------------------------- Hungarian --------------------------------
def _hu_word(w):
    s = w.replace("dzs", "ʤ").replace("dz", "ʣ")
    s = s.replace("sz", "S").replace("zs", "ʒ").replace("cs", "ʧ")
    s = s.replace("gy", "ɟ").replace("ny", "ɲ").replace("ty", "C").replace("ly", "j")
    s = s.replace("c", "ʦ").replace("C", "c")            # orthographic c->ʦ; ty placeholder->c
    s = s.replace("s", "ʃ").replace("S", "s")            # remaining s->ʃ; sz placeholder->s
    s = s.replace("a", "ɒ").replace("e", "ɛ").replace("ö", "ø").replace("ü", "y")
    s = (s.replace("á", "aː").replace("é", "eː").replace("í", "iː").replace("ó", "oː")
         .replace("ő", "øː").replace("ú", "uː").replace("ű", "yː"))
    s = s.replace("g", "ɡ")
    return re.sub(r"([bdfɡhklmnprtvz])\1", r"\1ː", s)     # gemination


# -------------------------------- Basque ----------------------------------
def _eu_word(w):
    s = w.replace("tx", "ʧ").replace("tz", "ʦ").replace("ts", "ʦ")
    s = s.replace("tt", "c").replace("dd", "ɟ")
    s = s.replace("x", "ʃ").replace("ñ", "ɲ").replace("ll", "ʎ")
    return s.replace("z", "s").replace("h", "").replace("g", "ɡ")


# ------------------------------- Haitian ----------------------------------
def _ht_word(w):
    s = w.replace("ou", "u").replace("an", "ã").replace("on", "ɔ̃").replace("en", "ẽ")
    s = s.replace("ch", "ʃ").replace("j", "ʒ").replace("y", "j")
    s = s.replace("ê", "ɛ").replace("è", "ɛ").replace("ò", "ɔ").replace("é", "e")
    return s.replace("r", "ɣ").replace("g", "ɡ")


_LANG = {"epo": _eo_word, "fin": _fi_word, "deu": _de_word,
         "tur": _tr_word, "gag": _tr_word, "krc": _tr_word, "als": _sq_word,
         "pol": _pl_word, "hun": _hu_word, "eus": _eu_word, "hat": _ht_word}
_CONF = {"epo": "high", "fin": "high", "deu": "medium", "tur": "high", "gag": "high",
         "krc": "medium", "als": "high", "pol": "medium", "hun": "medium",
         "eus": "high", "hat": "medium"}


def to_ipa(text, lang):
    fn = _LANG[lang]
    text = unicodedata.normalize("NFC", text).strip().lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    out = []
    keep = lambda c: c.isalpha() or c in " '"           # keep all Unicode letters
    for alt in _SEP.split(text):
        alt = "".join(c if keep(c) else " " for c in alt).strip()
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
    "tur": [("göz", "ɡøz"), ("diş", "diʃ"), ("büyük", "byjyk"), ("gece", "ɡeʤe"),
            ("yıldız", "jɯldɯz")],
    "als": [("gjuhë", "ɟuhə"), ("dhëmb", "ðəmb"), ("qen", "cen"), ("yll", "yɫ"),
            ("zjarr", "zjar")],
    "pol": [("woda", "voda"), ("język", "jɛzɨk"), ("ząb", "zɔb"), ("duży", "duʒɨ"),
            ("słońce", "swoɲʦe"), ("czas", "ʧas")],
    "hun": [("víz", "viːz"), ("tűz", "tyːz"), ("nyelv", "ɲɛlv"), ("szem", "sɛm"),
            ("kettő", "kɛtːøː"), ("nagy", "nɒɟ"), ("csillag", "ʧilːɒɡ")],
    "eus": [("txakur", "ʧakur"), ("hortz", "orʦ"), ("izar", "isar"), ("haundi", "aundi"),
            ("eguzki", "eɡuski")],
    "hat": [("dlo", "dlo"), ("solêy", "solɛj"), ("je", "ʒe"), ("dife", "dife")],
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
