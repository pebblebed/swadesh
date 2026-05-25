#!/usr/bin/env python3
"""Romance G2P: Spanish / Italian / Portuguese / French orthography -> broad IPA.

These are the deferred national-orthography lists (latin_diacritic / plain_ascii);
each needs real per-language rules. BROAD PHONEMIC, not narrow: we don't mark stress
or fine allophony (Spanish b/β, Portuguese vowel reduction, etc.). Reliability by
language: Spanish & Italian very high (near-phonemic spelling); Portuguese moderate
(nasal vowels, s/x voicing); French low-moderate (deep orthography: silent finals,
nasal vowels, vowel digraphs) -- the French output is acknowledged-noisy.

Affricates are emitted as the single codepoints ʧ ʤ ʦ ʣ, which scripts/ipa_features
folds to the tie-bar forms t͡ʃ d͡ʒ t͡s d͡z. Nasal vowels use a combining tilde.

Run `python scripts/romance_g2p.py` for the embedded self-tests.
"""
import re
import unicodedata

V = "aeiouáéíóúàèìòùâêôãõäëïöüâ"            # any vowel letter (for context tests)
FRONT = "eiéèêiíì"                          # front vowels that soften c/g


def _alts(text):
    """Split a raw cell into alternants (synonyms) and strip parentheticals/junk."""
    text = unicodedata.normalize("NFC", text).strip().lower()
    text = re.sub(r"\([^)]*\)", " ", text)                 # drop (m.)/(v.) notes
    parts = re.split(r"[,;/]", text)
    return [re.sub(r"[^a-zà-ÿ' ]", " ", p).strip() for p in parts]


# ------------------------------- Spanish ----------------------------------
def _es_word(w):
    s = w
    s = s.replace("ch", "ʧ").replace("ll", "ʎ").replace("ñ", "ɲ")
    s = s.replace("x", "ks")                               # orthographic x -> ks (before we mint /x/)
    s = re.sub(r"^r", "ʀ", s)                              # initial r = trill (placeholder)
    s = s.replace("rr", "ʀ")
    s = s.replace("r", "ɾ").replace("ʀ", "r")             # single r = tap, trill back to r
    s = re.sub(r"qu([" + FRONT + "])", r"k\1", s)         # que/qui -> k
    s = s.replace("qu", "kw").replace("q", "k")
    s = re.sub(r"gu([" + FRONT + "])", r"ɡ\1", s)         # gue/gui -> ɡ (u silent)
    s = s.replace("gü", "ɡw").replace("ü", "u")
    s = re.sub(r"g([" + FRONT + "])", r"x\1", s)          # ge/gi -> x
    s = s.replace("g", "ɡ").replace("j", "x")
    s = re.sub(r"c([" + FRONT + "])", r"θ\1", s)          # ce/ci -> θ (distinción)
    s = s.replace("z", "θ").replace("c", "k")             # remaining c -> k
    s = s.replace("v", "b").replace("h", "")
    s = re.sub(r"y([" + V + "])", r"j\1", s).replace("y", "i")
    return _strip_acc(s)


# ------------------------------- Italian ----------------------------------
def _it_word(w):
    s = w
    s = re.sub(r"sc([ei])", r"ʃ\1", s)                    # sce/sci -> ʃ
    s = re.sub(r"sci([" + V + "])", r"ʃ\1", s)            # scia/scio -> ʃ (i silent)
    s = s.replace("sch", "sk")
    s = re.sub(r"ci([" + V + "])", r"ʧ\1", s)             # cia/cio -> ʧ (i silent)
    s = re.sub(r"gi([" + V + "])", r"ʤ\1", s)             # gia/gio -> ʤ
    s = s.replace("ch", "k").replace("gh", "ɡ")
    s = s.replace("gli", "ʎ").replace("gn", "ɲ")
    s = re.sub(r"c([ei])", r"ʧ\1", s)                     # ce/ci -> ʧ
    s = re.sub(r"g([ei])", r"ʤ\1", s)                     # ge/gi -> ʤ
    s = s.replace("c", "k").replace("g", "ɡ")
    s = s.replace("qu", "kw").replace("q", "k")
    s = s.replace("z", "ʦ").replace("h", "")
    s = re.sub(r"([bcdfɡklmnprstv])\1", r"\1ː", s)        # geminate -> long
    s = re.sub(r"ʦʦ", "ʦː", s)
    return _strip_acc(s)


# ------------------------------ Portuguese --------------------------------
def _pt_word(w):
    s = w
    s = s.replace("ã", "ɐ̃").replace("õ", "õ")
    s = s.replace("lh", "ʎ").replace("nh", "ɲ").replace("ch", "ʃ")
    s = s.replace("ç", "s")
    s = re.sub(r"c([ei])", r"s\1", s).replace("c", "k")
    s = re.sub(r"gu([ei])", r"ɡ\1", s)
    s = re.sub(r"g([ei])", r"ʒ\1", s).replace("g", "ɡ").replace("j", "ʒ")
    s = s.replace("qu", "kw").replace("q", "k")
    # vowel + m/n before consonant or word-final -> nasal vowel (drop the nasal)
    s = re.sub(r"([aeiouɐ])[mn](?=[^aeiouɐ]|$)", lambda m: _nasal(m.group(1)), s)
    s = re.sub(r"([" + V + "])s([" + V + "])", r"\1z\2", s)   # intervocalic s -> z
    s = s.replace("ss", "s").replace("x", "ʃ")
    s = re.sub(r"^r", "ʁ", s).replace("rr", "ʁ").replace("r", "ɾ").replace("ʁ", "ʁ")
    s = s.replace("h", "")
    return _strip_acc(s)


def _nasal(v):
    return {"a": "ɐ̃", "e": "ẽ", "i": "ĩ", "o": "õ", "u": "ũ", "ɐ": "ɐ̃"}.get(v, v + "̃")


# -------------------------------- French ----------------------------------
def _fr_word(w):
    s = w
    s = s.replace("eau", "o").replace("au", "o").replace("ou", "u")
    s = s.replace("oi", "wa").replace("ai", "ɛ").replace("ei", "ɛ")
    s = s.replace("eu", "ø").replace("œu", "ø").replace("œ", "ø")
    s = re.sub(r"ien(?=[^aeiouéèêy]|$)", "Jɛ̃", s)        # -ien -> jɛ̃ (J = glide placeholder)
    # nasal vowels (before consonant / word end, not before another vowel)
    s = re.sub(r"(ai|ei|i)n(?=[^aeiouéèêy]|$)", "ɛ̃", s)
    s = re.sub(r"[ae][mn](?=[^aeiouéèêy]|$)", "ɑ̃", s)
    s = re.sub(r"o[mn](?=[^aeiouéèêy]|$)", "ɔ̃", s)
    s = re.sub(r"u[mn](?=[^aeiouéèêy]|$)", "œ̃", s)
    s = re.sub(r"i[mn](?=[^aeiouéèêy]|$)", "ɛ̃", s)
    s = s.replace("ch", "ʃ").replace("gn", "ɲ").replace("ph", "f")
    s = re.sub(r"c([eiéè])", r"s\1", s).replace("ç", "s").replace("c", "k")
    s = re.sub(r"gu([eiéè])", r"ɡ\1", s)
    s = re.sub(r"g([eiéè])", r"ʒ\1", s).replace("g", "ɡ").replace("j", "ʒ")
    s = s.replace("qu", "k").replace("q", "k")
    s = s.replace("ill", "iJ").replace("il", "J")         # glide (placeholder J)
    s = re.sub(r"([" + V + "])s([" + V + "])", r"\1z\2", s).replace("ss", "s")
    s = s.replace("r", "ʁ").replace("h", "")
    s = re.sub(r"ent$", "", s)                            # silent verbal -ent
    s = re.sub(r"[tdspxz]$", "", s)                       # silent final consonant (broad)
    s = re.sub(r"e$", "", s)                              # silent final e
    s = s.replace("y", "i").replace("J", "j")             # resolve glide placeholder
    return _strip_acc(s)


_ACC = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "à": "a", "è": "e",
        "ì": "i", "ò": "o", "ù": "u", "â": "a", "ê": "e", "î": "i", "ô": "o",
        "û": "u", "ä": "a", "ë": "e", "ï": "i", "ö": "o", "ü": "u", " â": "a"}


def _strip_acc(s):
    return "".join(_ACC.get(c, c) for c in s)


_LANG = {"spa": _es_word, "ita": _it_word, "por": _pt_word, "fra": _fr_word}


def to_ipa(text, lang):
    """Convert a raw orthographic cell to broad IPA for `lang` in spa/ita/por/fra.
    Returns (ipa, confidence). Confidence reflects per-language reliability."""
    fn = _LANG[lang]
    out = []
    for alt in _alts(text):
        if not alt:
            continue
        ipa = " ".join(fn(w) for w in alt.split() if w)
        if ipa and ipa not in out:
            out.append(ipa)
    conf = {"spa": "high", "ita": "high", "por": "medium", "fra": "low"}[lang]
    return ", ".join(out), conf


# ------------------------------- self-test --------------------------------
_TESTS = {
    "spa": [("perro", "pero"), ("fuego", "fueɡo"), ("cinco", "θinko"),
            ("general", "xeneɾal"), ("queso", "keso"), ("año", "aɲo"),
            ("lluvia", "ʎubia"), ("hola", "ola"), ("yo", "jo"), ("jefe", "xefe")],
    "ita": [("cane", "kane"), ("cibo", "ʧibo"), ("gelato", "ʤelato"),
            ("gnomo", "ɲomo"), ("figlio", "fiʎo"), ("pesce", "peʃe"),
            ("zio", "ʦio"), ("notte", "notːe"), ("chiave", "kiave")],
    "por": [("chave", "ʃave"), ("filho", "fiʎo"), ("casa", "kaza"),
            ("gente", "ʒẽte"), ("cinco", "sĩko"), ("rato", "ʁato")],
    "fra": [("chien", "ʃjɛ̃"), ("feu", "fø"), ("grand", "ɡʁɑ̃"),
            ("rouge", "ʁuʒ"), ("eau", "o")],
}


def selftest():
    fails = 0
    for lang, cases in _TESTS.items():
        for src, want in cases:
            got = _LANG[lang](src)
            got, want = unicodedata.normalize("NFC", got), unicodedata.normalize("NFC", want)
            if got != want:
                fails += 1
                print(f"FAIL {lang} {src!r}: got {got!r} want {want!r}")
    n = sum(len(v) for v in _TESTS.values())
    print(f"romance_g2p self-test: {n - fails}/{n} passed")
    return fails


if __name__ == "__main__":
    import sys
    sys.exit(1 if selftest() else 0)
