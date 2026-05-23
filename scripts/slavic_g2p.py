#!/usr/bin/env python3
"""Czech & Slovak grapheme->IPA conversion (Tier 1 of the IPA strategy).

Czech (ces) and Slovak (slk) write their transcriptions in native Latin
orthography, which is highly phonemic -- so a deterministic rule set converts
them to IPA far more reliably than any off-the-shelf G2P for a low-resource
language. They were split out of the Americanist Tier-1 handler because their
carons (c v s v z v ...) are ORTHOGRAPHY, not Americanist phonetic notation, and
would be mis-converted by a flat caron->IPA table.

What this implements (per word):
  1. Digraphs:  ch->x; (Slovak) dz->d͡z, dž->d͡ʒ.
  2. Palatalization: explicit ď ť ň (+ Slovak ľ) -> ɟ c ɲ ʎ; and plain d t n
     (+ Slovak l) before a SOFT vowel -> the same palatals.
        - Czech soft vowels: i í ě   (y/ý keep the consonant hard, by design).
        - Slovak soft vowels: i í and the i-initial diphthongs ia ie iu.
     Czech ě also palatalizes/inserts a glide: dě tě ně -> ɟɛ cɛ ɲɛ;
     bě pě vě fě -> bjɛ pjɛ vjɛ fjɛ; mě -> mɲɛ.
  3. Vowels incl. length: á é í ó ú ů ý -> Vː; Czech short i/y=ɪ o=o,
     Slovak i/y=i o=ɔ ä=æ; Slovak diphthongs ia ie iu=i̯a i̯ɛ i̯u, ô=u̯ɔ;
     Czech ou au eu=ou̯ au̯ ɛu̯.
  4. Syllabic liquids: r l with no adjacent vowel -> r̩ l̩ (Slovak ĺ ŕ -> l̩ː r̩ː).
  5. n -> ŋ before a velar (k ɡ).
  6. Regressive voicing assimilation across obstruent clusters + word-final
     devoicing (kde->ɡdɛ, vták->ftaːk, zub->zup, dážď->daːʃc). v and Czech ř
     are TARGETS of assimilation but not TRIGGERS (v doesn't voice a preceding
     obstruent; ř instead devoices PROGRESSIVELY after a voiceless one: tři->tr̝̥ɪ).

Known, documented limitations (faithful-to-orthography, conservative):
  - Slovak d/t/n/l before plain 'e' are NOT palatalized. Slovak softening before
    e is lexical (ten=[tɛn] but deň=[ɟɛɲ]); we default to the majority "hard"
    reading. Affects a handful of words (deň, deliť, ...). Softening before i/í
    and the i-diphthongs (the regular cases) IS applied.
  - 'dz'/'dž' are read as affricates (right for native words like hádzať=ɦaːd͡zac;
    would be wrong only across a morpheme boundary, none in this corpus).
  - We transcribe what is written: source typos (Czech 'déšt', 'ohen', 'nnoc';
    Slovak 'dážť') convert literally.

Run `python scripts/slavic_g2p.py` to execute the embedded self-test.
"""
import re
import unicodedata

# --- combining marks / multi-codepoint symbols, named to avoid mistyping ---
TIE = "͡"      # combining double inverted breve (affricate tie bar)
SYLL = "̩"     # combining vertical line below (syllabic)
NSY = "̯"      # combining inverted breve below (non-syllabic / glide)
RAISED = "̝"   # combining up tack below (raised) -- Czech ř
RING = "̥"     # combining ring below (voiceless)
LONG = "ː"     # ː length mark

TS, DZ = "t" + TIE + "s", "d" + TIE + "z"
TSH, DZH = "t" + TIE + "ʃ", "d" + TIE + "ʒ"
RZ, RZ_VL = "r" + RAISED, "r" + RAISED + RING  # Czech ř voiced / voiceless

# Obstruent inventory: ipa -> (voiceless_form, voiced_form, is_trigger).
# is_trigger=False => does not impose its voicing on a preceding obstruent
# (true for v, and for Czech ř which devoices progressively instead).
OBST = {
    "p": ("p", "b", True),   "b": ("p", "b", True),
    "t": ("t", "d", True),   "d": ("t", "d", True),
    "c": ("c", "ɟ", True),   "ɟ": ("c", "ɟ", True),     # palatal stops (ť/ď)
    "k": ("k", "ɡ", True),   "ɡ": ("k", "ɡ", True),
    "f": ("f", "v", True),   "v": ("f", "v", False),    # v: target, not trigger
    "s": ("s", "z", True),   "z": ("s", "z", True),
    "ʃ": ("ʃ", "ʒ", True),   "ʒ": ("ʃ", "ʒ", True),
    "x": ("x", "ɣ", True),   "ɣ": ("x", "ɣ", True),
    "ɦ": ("x", "ɦ", True),                              # h voiced; devoices to x
    TS: (TS, DZ, True),      DZ: (TS, DZ, True),
    TSH: (TSH, DZH, True),   DZH: (TSH, DZH, True),
    RZ: (RZ_VL, RZ, False),  RZ_VL: (RZ_VL, RZ, False), # ř: target, not trigger
}
SON = {"m", "n", "ɲ", "ŋ", "r", "l", "ʎ", "j"}
VELAR = {"k", "ɡ"}


def _mk(ipa):
    """Build a phoneme record. Category O(bstruent)/S(onorant)/V(owel)."""
    if ipa in OBST:
        vl, vd, trig = OBST[ipa]
        return {"ipa": ipa, "cat": "O", "vl": vl, "vd": vd,
                "trig": trig, "voiced": ipa == vd}
    if ipa in SON:
        return {"ipa": ipa, "cat": "S"}
    return {"ipa": ipa, "cat": "V"}  # vowels, long vowels, diphthongs, æ


# ------------------------- per-language tokenizers -------------------------

_CZ = {
    "a": "a", "á": "aː", "e": "ɛ", "é": "ɛː", "i": "ɪ", "í": "iː",
    "o": "o", "ó": "oː", "u": "u", "ú": "uː", "ů": "uː", "y": "ɪ", "ý": "iː",
    "b": "b", "c": TS, "č": TSH, "d": "d", "ď": "ɟ", "f": "f", "g": "ɡ",
    "h": "ɦ", "j": "j", "k": "k", "l": "l", "m": "m", "n": "n", "ň": "ɲ",
    "p": "p", "q": "k", "r": "r", "ř": RZ, "s": "s", "š": "ʃ", "t": "t",
    "ť": "c", "v": "v", "w": "v", "z": "z", "ž": "ʒ",
}
_CZ_SOFT = set("iíě")            # palatalize preceding d/t/n
_CZ_PAL = {"d": "ɟ", "t": "c", "n": "ɲ"}
_CZ_DIPH = {"ou": "o" + "u" + NSY, "au": "a" + "u" + NSY, "eu": "ɛ" + "u" + NSY}


def _tokenize_czech(w):
    out, residual, i, n = [], set(), 0, len(w)
    while i < n:
        c, nxt, two = w[i], (w[i + 1] if i + 1 < n else ""), w[i:i + 2]
        if two == "ch":
            out.append(_mk("x")); i += 2; continue
        if two in _CZ_DIPH:
            out.append(_mk(_CZ_DIPH[two])); i += 2; continue
        if c in "dtn" and nxt in _CZ_SOFT:           # di/ti/ni, dí.., dě/tě/ně
            out.append(_mk(_CZ_PAL[c])); i += 1; continue
        if c in "bpvf" and nxt == "ě":               # bě pě vě fě -> Cjɛ
            out.append(_mk(_CZ[c])); out.append(_mk("j")); out.append(_mk("ɛ"))
            i += 2; continue
        if c == "m" and nxt == "ě":                  # mě -> mɲɛ
            out.append(_mk("m")); out.append(_mk("ɲ")); out.append(_mk("ɛ"))
            i += 2; continue
        if c == "ě":                                 # ě after d/t/n (cons already palatalized)
            out.append(_mk("ɛ")); i += 1; continue
        if c == "x":
            out.append(_mk("k")); out.append(_mk("s")); i += 1; continue
        if c in _CZ:
            out.append(_mk(_CZ[c])); i += 1; continue
        residual.add(c); out.append({"ipa": c, "cat": "X"}); i += 1
    return out, residual


_SK = {
    "a": "a", "á": "aː", "ä": "æ", "e": "ɛ", "é": "ɛː", "i": "i", "í": "iː",
    "o": "ɔ", "ó": "ɔː", "u": "u", "ú": "uː", "y": "i", "ý": "iː",
    "b": "b", "c": TS, "č": TSH, "d": "d", "ď": "ɟ", "f": "f", "g": "ɡ",
    "h": "ɦ", "j": "j", "k": "k", "l": "l", "ľ": "ʎ", "m": "m", "n": "n",
    "ň": "ɲ", "p": "p", "q": "k", "r": "r", "s": "s", "š": "ʃ", "t": "t",
    "ť": "c", "v": "v", "w": "v", "z": "z", "ž": "ʒ",
}
_SK_SOFT = set("ií")             # +i-initial diphthongs (ia/ie/iu start with i)
_SK_PAL = {"d": "ɟ", "t": "c", "n": "ɲ", "l": "ʎ"}
_SK_DIPH = {"ia": "i" + NSY + "a", "ie": "i" + NSY + "ɛ", "iu": "i" + NSY + "u"}


def _tokenize_slovak(w):
    out, residual, i, n = [], set(), 0, len(w)
    while i < n:
        c, nxt, two = w[i], (w[i + 1] if i + 1 < n else ""), w[i:i + 2]
        if two == "ch":
            out.append(_mk("x")); i += 2; continue
        if two == "dz":
            out.append(_mk(DZ)); i += 2; continue
        if two == "dž":
            out.append(_mk(DZH)); i += 2; continue
        if c in "dtnl" and nxt in _SK_SOFT:          # before i/í and ia/ie/iu
            out.append(_mk(_SK_PAL[c])); i += 1; continue
        if two in _SK_DIPH:
            out.append(_mk(_SK_DIPH[two])); i += 2; continue
        if c == "ô":
            out.append(_mk("u" + NSY + "ɔ")); i += 1; continue
        if c == "ĺ":                                 # long syllabic l
            out.append({"ipa": "l" + SYLL + LONG, "cat": "S"}); i += 1; continue
        if c == "ŕ":                                 # long syllabic r
            out.append({"ipa": "r" + SYLL + LONG, "cat": "S"}); i += 1; continue
        if c == "x":
            out.append(_mk("k")); out.append(_mk("s")); i += 1; continue
        if c in _SK:
            out.append(_mk(_SK[c])); i += 1; continue
        residual.add(c); out.append({"ipa": c, "cat": "X"}); i += 1
    return out, residual


# ------------------------- shared post-processing -------------------------

def _postprocess(ph):
    n = len(ph)

    # (a) n -> ŋ before a velar obstruent
    for i in range(n - 1):
        if ph[i].get("ipa") == "n" and ph[i + 1]["cat"] == "O" \
                and ph[i + 1]["ipa"] in VELAR:
            ph[i]["ipa"] = "ŋ"

    # (b) syllabic r/l: a liquid with no vowel on either side (word edge counts
    #     as non-vowel) becomes syllabic.
    for i in range(n):
        if ph[i]["cat"] == "S" and ph[i]["ipa"] in ("r", "l"):
            prev_v = i > 0 and ph[i - 1]["cat"] == "V"
            next_v = i < n - 1 and ph[i + 1]["cat"] == "V"
            if not prev_v and not next_v:
                ph[i]["ipa"] += SYLL

    # (c) regressive voicing assimilation + final devoicing (right to left).
    for i in range(n - 1, -1, -1):
        p = ph[i]
        if p["cat"] != "O":
            continue
        nxt = ph[i + 1] if i + 1 < n else None
        if nxt is None:                              # word-final -> devoice
            voiced = False
        elif nxt["cat"] == "O" and nxt["trig"]:      # assimilate to next obstruent
            voiced = nxt["voiced"]
        else:                                        # before sonorant/vowel/v -> keep
            voiced = (p["ipa"] == p["vd"])
        p["voiced"] = voiced
        p["ipa"] = p["vd"] if voiced else p["vl"]

    # (d) Czech ř devoices PROGRESSIVELY after a voiceless obstruent (tři, při).
    for i in range(n):
        if ph[i]["ipa"] == RZ:
            prev = ph[i - 1] if i > 0 else None
            if prev is not None and prev["cat"] == "O" and not prev["voiced"]:
                ph[i]["ipa"] = RZ_VL
                ph[i]["voiced"] = False

    # (e) Coalesce a homorganic alveolar stop into a following alveolar affricate
    #     (srdce: ...d.c... -> ...t.t͡s... -> ...t͡s...). The stop's place/voicing
    #     already matches the affricate after assimilation, so it merges.
    merged = []
    for i, p in enumerate(ph):
        nxt = ph[i + 1] if i + 1 < len(ph) else None
        if p["ipa"] in ("t", "d") and nxt is not None and nxt["ipa"] in (TS, DZ):
            continue  # drop the stop; the affricate carries it
        merged.append(p)

    return "".join(p["ipa"] for p in merged)


def _word_to_ipa(word, lang):
    tok = _tokenize_czech if lang == "ces" else _tokenize_slovak
    ph, residual = tok(word)
    return _postprocess(ph), residual


# ------------------------------ public API --------------------------------

_PAREN = re.compile(r"\([^)]*\)|\[[^\]]*\]")   # (m.), [optional] annotations
_PUNCT = re.compile(r"[.\"'!?]")               # stray punctuation
_SEG = re.compile(r"[,/;]")                     # synonym / variant separators


def to_ipa(transcription, lang):
    """Convert a normalized Czech/Slovak transcription to IPA.

    Handles multi-word forms (split on space) and synonym lists (split on , / ;),
    rejoining synonyms with ', '. Returns (ipa, residual_set); residual holds any
    source character that had no mapping (expected empty for clean ces/slk input).
    """
    text = _PUNCT.sub(" ", _PAREN.sub(" ", unicodedata.normalize("NFC", transcription).lower()))
    residual, segments = set(), []
    for seg in _SEG.split(text):
        words = []
        for wd in seg.split():
            ipa, res = _word_to_ipa(wd, lang)
            residual |= res
            if ipa:
                words.append(ipa)
        if words:
            segments.append(" ".join(words))
    return ", ".join(segments), residual


# ------------------------------ self-test ---------------------------------
# Gold forms derived by hand from Czech/Slovak phonology; exercises digraphs,
# palatalization, diphthongs, syllabic liquids, voicing assimilation, final
# devoicing, and the ř/ŋ special cases.
_TESTS = [
    # Czech
    ("ces", "kde", "ɡdɛ"), ("ces", "kdo", "ɡdo"),
    ("ces", "tři", "tr̝̥ɪ"), ("ces", "při", "pr̝̥ɪ"),
    ("ces", "čtyři", "t͡ʃtɪr̝ɪ"), ("ces", "řeka", "r̝ɛka"),
    ("ces", "pět", "pjɛt"), ("ces", "měsíc", "mɲɛsiːt͡s"),
    ("ces", "země", "zɛmɲɛ"), ("ces", "dvě", "dvjɛ"),
    ("ces", "člověk", "t͡ʃlovjɛk"), ("ces", "hvězda", "ɦvjɛzda"),
    ("ces", "sníh", "sɲiːx"), ("ces", "zub", "zup"), ("ces", "muž", "muʃ"),
    ("ces", "krev", "krɛf"), ("ces", "roh", "rox"), ("ces", "krk", "kr̩k"),
    ("ces", "dlouhý", "dlou̯ɦiː"), ("ces", "vidět", "vɪɟɛt"),
    ("ces", "studený", "studɛniː"), ("ces", "všechno", "fʃɛxno"),
    ("ces", "břicho", "br̝ɪxo"), ("ces", "chodidlo", "xoɟɪdlo"),
    ("ces", "vítr", "viːtr̩"), ("ces", "jméno", "jmɛːno"),
    ("ces", "srdce", "sr̩t͡sɛ"),
    # Slovak
    ("slk", "kde", "ɡdɛ"), ("slk", "dieťa", "ɟi̯ɛca"),
    ("slk", "vedieť", "vɛɟi̯ɛc"), ("slk", "list", "ʎist"),
    ("slk", "nie", "ɲi̯ɛ"), ("slk", "oni", "ɔɲi"),
    ("slk", "dážď", "daːʃc"), ("slk", "ťažký", "caʃkiː"),
    ("slk", "hladký", "ɦlatkiː"), ("slk", "vlhký", "vl̩xkiː"),
    ("slk", "dlhý", "dl̩ɦiː"), ("slk", "žltý", "ʒl̩tiː"),
    ("slk", "slnko", "sl̩ŋkɔ"), ("slk", "krv", "kr̩f"),
    ("slk", "úzky", "uːski"), ("slk", "vták", "ftaːk"),
    ("slk", "všetko", "fʃɛtkɔ"), ("slk", "kôra", "ku̯ɔra"),
    ("slk", "mäso", "mæsɔ"), ("slk", "lietať", "ʎi̯ɛtac"),
    ("slk", "letieť", "lɛci̯ɛc"), ("slk", "myslieť", "misʎi̯ɛc"),
    ("slk", "chrbát", "xr̩baːt"), ("slk", "hrízť", "ɦriːsc"),
    ("slk", "päť", "pæc"), ("slk", "rieka", "ri̯ɛka"),
    ("slk", "muž", "muʃ"), ("slk", "hádzať", "ɦaːd͡zac"),
    ("slk", "vrhať", "vr̩ɦac"),
    # multi-word / synonym / annotation handling
    ("slk", "báť sa", "baːc sa"), ("slk", "ten (m.)", "tɛn"),
    ("ces", "pít, pití", "piːt, pɪciː"),
]


def selftest():
    fails = 0
    for lang, word, want in _TESTS:
        got, _ = to_ipa(word, lang)
        want = unicodedata.normalize("NFC", want)
        got = unicodedata.normalize("NFC", got)
        ok = got == want
        fails += not ok
        if not ok:
            print(f"FAIL {lang} {word!r}: got {got!r}  want {want!r}")
    total = len(_TESTS)
    print(f"slavic_g2p self-test: {total - fails}/{total} passed")
    return fails


if __name__ == "__main__":
    import sys
    sys.exit(1 if selftest() else 0)
