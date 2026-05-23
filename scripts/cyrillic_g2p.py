#!/usr/bin/env python3
"""Russian & Bulgarian Cyrillic -> IPA conversion (Tier 2 of the IPA strategy).

The three Cyrillic-script lists are rus (Russian), bul (Bulgarian) and mdf
(Moksha). This module handles the two SLAVIC ones, whose Cyrillic orthography
maps to IPA by a deterministic rule set. Moksha (Uralic) is deferred -- it needs
language-specific rules (different palatalization, the reduced vowel, voiceless
sonorants) and separate verification.

BROAD PHONEMIC, no vowel reduction. None of these lists mark stress, and Russian/
Bulgarian vowel reduction (akanye/ikanye: unstressed o->[ɐ], etc.) is
stress-dependent -- so it is NOT recoverable from the text and is deliberately
NOT applied. Everything that IS recoverable from spelling is done properly:
palatalization, iotation, regressive voicing assimilation, and final devoicing.
(For cross-list comparison a reduction-free phonemic form is arguably better
anyway -- reduction is allophonic noise.)

RUSSIAN (rus), per word:
  - Palatalization: a palatalizable consonant before a soft vowel (я е ё ю и) or
    ь is palatalized (Cʲ); hard л -> ɫ, soft л -> lʲ. ж ш ц are always hard
    (after them и->ɨ, е->ɛ); ч щ are always soft (т͡ɕ, ɕː); й -> j.
  - Iotation: я е ё ю after a consonant -> the plain vowel (a e o u) on the now
    palatalized consonant; word-initially / after a vowel / after ъ ь -> j+vowel
    (я->ja ...). и after a consonant -> i; after ъ/ь -> ji.
  - Vowels: а=a э=ɛ ы=ɨ о=o у=u (я е ё ю и as above). ъ/ь are silent (ъ a hard
    separator, ь the palatalization sign).
  - Consonants: б=b в=v г=ɡ д=d ж=ʐ з=z к=k м=m н=n п=p р=r с=s т=t ф=f х=x
    ц=t͡s ч=t͡ɕ ш=ʂ щ=ɕː.

BULGARIAN (bul), per word:
  - 6 vowels а=a ъ=ɤ о=ɔ у=u е=ɛ и=i (ъ is a VOWEL here, not a hard sign; no
    ы/э/ё). Palatalization ONLY before я ю and ь (Cʲa, Cʲu) -- consonants are
    NOT palatalized before е/и (ден=dɛn, not dʲɛn). й -> j.
  - Consonants as Russian except ж=ʒ ш=ʃ ч=t͡ʃ (not retroflex/alveolo-palatal),
    щ=ʃt, and the digraphs дж=d͡ʒ дз=d͡z; л=l (not velarized).

Shared: regressive voicing assimilation across obstruent clusters + word-final
devoicing (зуб->zup, гръб->ɡrɤp, водка->votka, сделать->zdʲelatʲ). в is a TARGET
of assimilation but not a TRIGGER (тв stays voiceless), matching the Slavic v.

Known, documented limitations (faithful, conservative):
  - No vowel reduction / no stress (see above).
  - We transcribe the spelling: lexical exceptions are read literally
    (что -> t͡ɕto, not the spoken ʂto; солнце keeps its written л).

MOKSHA (mdf), per word -- a Uralic language, so the rules differ from the Slavic
two (verified against the corpus):
  - Palatalization is CORONAL-ONLY: т д н с з ц л р palatalize before a soft vowel
    (е и я ё ю) or ь; labials/velars/post-alveolars do NOT (кяль=kælʲ not kʲælʲ).
  - Vowels: а=a о=o у=u; soft е=e и=i я=æ ё=o ю=u (я is the front /æ/!). э is the
    word-initial / "hard" /e/ (эди=edi); after a vowel or word-initially a soft
    vowel takes a j-glide (ёрдамс=jordams, шяярь=ʃæjærʲ); и never glides.
  - Voiceless sonorants, written with х: лх=l̥ рх=r̥ льх=l̥ʲ рьх=r̥ʲ йх=j̊
    (шалхка=ʃal̥ka, эрьхке=er̥ʲke, мархта=mar̥ta).
  - ж=ʒ ш=ʃ ч=t͡ʃ ц=t͡s. NO final devoicing and NO voicing assimilation (Uralic;
    voiced finals stay -- од=od, кев=kev, сялдаз=sʲældaz, кальдяв=kalʲdʲæv).

Run `python scripts/cyrillic_g2p.py` to execute the embedded self-test.
"""
import re
import unicodedata

TIE = "͡"   # combining double inverted breve (affricate tie bar)
PAL = "ʲ"  # modifier letter small j (palatalized)
LONG = "ː"
RING = "̥"   # combining ring below (voiceless) -- Moksha voiceless sonorants
RING_ABOVE = "̊"  # combining ring above (voiceless j)

TS, DZ = "t" + TIE + "s", "d" + TIE + "z"
TSH, DZH = "t" + TIE + "ʃ", "d" + TIE + "ʒ"      # Bulgarian ч / дж
TCC, DZC = "t" + TIE + "ɕ", "d" + TIE + "ʑ"      # Russian ч / its voiced pair
SHCH = "ɕ" + LONG                                 # Russian щ
SHCH_VD = "ʑ" + LONG

# Obstruent base -> (voiceless, voiced, is_trigger). Palatalization is carried
# separately (the `pal` field), so each base appears once.
BASE = {
    "p": ("p", "b", True),   "b": ("p", "b", True),
    "t": ("t", "d", True),   "d": ("t", "d", True),
    "k": ("k", "ɡ", True),   "ɡ": ("k", "ɡ", True),
    "f": ("f", "v", True),   "v": ("f", "v", False),     # в: target, not trigger
    "s": ("s", "z", True),   "z": ("s", "z", True),
    "ʃ": ("ʃ", "ʒ", True),   "ʒ": ("ʃ", "ʒ", True),      # Bulgarian
    "ʂ": ("ʂ", "ʐ", True),   "ʐ": ("ʂ", "ʐ", True),      # Russian
    "x": ("x", "ɣ", True),                                # voiced allophone ɣ
    TS: (TS, DZ, True),      DZ: (TS, DZ, True),
    TSH: (TSH, DZH, True),   DZH: (TSH, DZH, True),
    TCC: (TCC, DZC, True),   DZC: (TCC, DZC, True),
    SHCH: (SHCH, SHCH_VD, True),
}
SON = {"m", "n", "r", "l", "ɫ", "j", "ʎ"}


def _mk(base, pal=""):
    """Phoneme record. Obstruents carry voicing fields; cat O/S/V."""
    if base in BASE:
        vl, vd, trig = BASE[base]
        return {"cat": "O", "vl": vl, "vd": vd, "trig": trig,
                "pal": pal, "voiced": base == vd, "ipa": base + pal}
    if base in SON:
        return {"cat": "S", "ipa": base + pal, "pal": pal}
    return {"cat": "V", "ipa": base + pal}


# ------------------------------- Russian ----------------------------------

_RU_C = {"б": "b", "в": "v", "г": "ɡ", "д": "d", "з": "z", "к": "k", "м": "m",
         "н": "n", "п": "p", "р": "r", "с": "s", "т": "t", "ф": "f", "х": "x"}
_RU_HARD_V = {"а": "a", "э": "ɛ", "ы": "ɨ", "о": "o", "у": "u"}
_RU_SOFT = set("яеёюи")
_RU_SOFT_PLAIN = {"я": "a", "е": "e", "ё": "o", "ю": "u", "и": "i"}
_RU_SIB_V = {"я": "a", "е": "ɛ", "ё": "o", "ю": "u", "и": "ɨ"}
_RU_SIB = {"ж": "ʐ", "ш": "ʂ", "ц": TS}     # always hard
_RU_INHERENT = {"ч": TCC, "щ": SHCH}        # always soft, no added ʲ


def _tokenize_russian(w):
    out, residual, prev, i, n = [], set(), None, 0, len(w)
    while i < n:
        c = w[i]
        nxt = w[i + 1] if i + 1 < n else ""
        if c in _RU_HARD_V:
            out.append(_mk(_RU_HARD_V[c])); prev = "V"
        elif c in _RU_SOFT:
            if prev in ("Cpal", "soft_cons"):
                out.append(_mk(_RU_SOFT_PLAIN[c]))
            elif prev == "Csib":
                out.append(_mk(_RU_SIB_V[c]))
            elif c == "и" and prev in ("V", None):
                out.append(_mk("i"))
            else:                                   # initial / after vowel / ъ ь
                out.append(_mk("j")); out.append(_mk(_RU_SOFT_PLAIN[c]))
            prev = "V"
        elif c == "ь":
            prev = "soft_b"
        elif c == "ъ":
            prev = "hard_b"
        elif c in _RU_SIB:
            out.append(_mk(_RU_SIB[c])); prev = "Csib"
        elif c in _RU_INHERENT:
            out.append(_mk(_RU_INHERENT[c])); prev = "soft_cons"
        elif c == "й":
            out.append(_mk("j")); prev = "Cother"
        elif c == "л":
            soft = nxt in _RU_SOFT or nxt == "ь"
            out.append(_mk("lʲ") if soft else _mk("ɫ"))
            prev = "Cpal" if soft else "Chard"
        elif c in _RU_C:
            soft = nxt in _RU_SOFT or nxt == "ь"
            out.append(_mk(_RU_C[c], PAL if soft else ""))
            prev = "Cpal" if soft else "Chard"
        else:
            residual.add(c); out.append({"cat": "X", "ipa": c}); prev = "V"
        i += 1
    return out, residual


# ------------------------------- Bulgarian --------------------------------

_BG_C = {"б": "b", "в": "v", "г": "ɡ", "д": "d", "з": "z", "к": "k", "м": "m",
         "н": "n", "п": "p", "р": "r", "с": "s", "т": "t", "ф": "f", "х": "x",
         "л": "l", "ц": TS}                          # ц palatalizable (цял=t͡sʲal)
_BG_V = {"а": "a", "ъ": "ɤ", "о": "ɔ", "у": "u", "е": "ɛ", "и": "i"}
_BG_SOFT = set("яю")
_BG_SOFT_PLAIN = {"я": "a", "ю": "u"}
_BG_SIB = {"ж": "ʒ", "ш": "ʃ", "ч": TSH}             # always hard


def _tokenize_bulgarian(w):
    out, residual, prev, i, n = [], set(), None, 0, len(w)
    while i < n:
        c = w[i]
        nxt = w[i + 1] if i + 1 < n else ""
        two = w[i:i + 2]
        if two == "дж":
            out.append(_mk(DZH)); prev = "Csib"; i += 2; continue
        if two == "дз":
            out.append(_mk(DZ)); prev = "Csib"; i += 2; continue
        if c in _BG_V:
            out.append(_mk(_BG_V[c])); prev = "V"
        elif c in _BG_SOFT:
            if prev == "Cpal":
                out.append(_mk(_BG_SOFT_PLAIN[c]))
            elif prev == "Csib":
                out.append(_mk(_BG_SOFT_PLAIN[c]))
            else:
                out.append(_mk("j")); out.append(_mk(_BG_SOFT_PLAIN[c]))
            prev = "V"
        elif c == "ь":
            prev = "soft_b"
        elif c == "щ":
            out.append(_mk("ʃ")); out.append(_mk("t")); prev = "Cother"
        elif c in _BG_SIB:
            out.append(_mk(_BG_SIB[c])); prev = "Csib"
        elif c == "й":
            out.append(_mk("j")); prev = "Cother"
        elif c in _BG_C:
            soft = nxt in _BG_SOFT or nxt == "ь"
            out.append(_mk(_BG_C[c], PAL if soft else ""))
            prev = "Cpal" if soft else "Chard"
        else:
            residual.add(c); out.append({"cat": "X", "ipa": c}); prev = "V"
        i += 1
    return out, residual


# ------------------------------- Moksha -----------------------------------

_MK_C = {"б": "b", "в": "v", "г": "ɡ", "д": "d", "ж": "ʒ", "з": "z", "к": "k",
         "л": "l", "м": "m", "н": "n", "п": "p", "р": "r", "с": "s", "т": "t",
         "ф": "f", "х": "x", "ц": TS, "ч": TSH, "ш": "ʃ", "щ": SHCH, "й": "j"}
_MK_CORONAL = set("тднсзцлр")          # only coronals palatalize in Moksha
_MK_SOFT = set("еияёю")
_MK_HARD_V = {"а": "a", "о": "o", "у": "u", "э": "e"}    # э = the "hard" /e/
_MK_SOFT_BASE = {"е": "e", "и": "i", "я": "æ", "ё": "o", "ю": "u"}   # я = /æ/
_MK_VL_SON = {"льх": "l" + RING + PAL, "рьх": "r" + RING + PAL,
              "лх": "l" + RING, "рх": "r" + RING, "йх": "j" + RING_ABOVE}


def _moksha_word(w):
    """Moksha grapheme->IPA. Returns (ipa, residual). No voicing post-processing
    (Moksha has neither final devoicing nor regressive assimilation)."""
    out, residual, prev, i, n = [], set(), None, 0, len(w)
    while i < n:
        three, two, c = w[i:i + 3], w[i:i + 2], w[i]
        if three in _MK_VL_SON:
            out.append(_MK_VL_SON[three]); prev = "C"; i += 3; continue
        if two in _MK_VL_SON:
            out.append(_MK_VL_SON[two]); prev = "C"; i += 2; continue
        if c in _MK_HARD_V:
            out.append(_MK_HARD_V[c]); prev = "V"
        elif c in _MK_SOFT:
            if prev == "C":
                out.append(_MK_SOFT_BASE[c])         # consonant absorbed the softness
            elif c == "и":
                out.append("i")                       # и never takes a j-glide
            else:
                out.append("j" + _MK_SOFT_BASE[c])    # initial / after vowel / after ь
            prev = "V"
        elif c == "ь":
            prev = "soft_b"                            # palatalization done via lookahead
        elif c in _MK_C:
            nxt = w[i + 1] if i + 1 < n else ""
            pal = PAL if (c in _MK_CORONAL and (nxt in _MK_SOFT or nxt == "ь")) else ""
            out.append(_MK_C[c] + pal)
            prev = "C"
        else:
            residual.add(c); out.append(c); prev = "V"
        i += 1
    return "".join(out), residual


# --------------------------- shared post-processing -----------------------

def _postprocess(ph):
    """Regressive voicing assimilation + word-final devoicing (right to left)."""
    n = len(ph)
    for i in range(n - 1, -1, -1):
        p = ph[i]
        if p["cat"] != "O":
            continue
        nxt = ph[i + 1] if i + 1 < n else None
        if nxt is None:                              # word-final -> devoice
            voiced = False
        elif nxt["cat"] == "O" and nxt["trig"]:      # assimilate to next obstruent
            voiced = nxt["voiced"]
        else:                                        # before sonorant/vowel/в -> keep
            voiced = p["voiced"]
        p["voiced"] = voiced
        p["ipa"] = (p["vd"] if voiced else p["vl"]) + p["pal"]
    return "".join(p["ipa"] for p in ph)


def _word_to_ipa(word, lang):
    if lang == "mdf":
        return _moksha_word(word)            # no voicing post-processing
    tok = _tokenize_russian if lang == "rus" else _tokenize_bulgarian
    ph, residual = tok(word)
    return _postprocess(ph), residual


# ------------------------------ public API --------------------------------

_PAREN = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_SEG = re.compile(r"[,/;]")


def to_ipa(transcription, lang):
    """Convert a normalized Russian/Bulgarian Cyrillic transcription to IPA.

    Handles multi-word forms and synonym lists (split on , / ;). Returns
    (ipa, residual_set); residual holds any source character with no mapping."""
    text = unicodedata.normalize("NFC", transcription).lower()
    text = _PAREN.sub(" ", text)
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


# ------------------------------- self-test --------------------------------
# Gold forms hand-derived from Russian/Bulgarian phonology (broad phonemic, no
# reduction): palatalization, iotation, ж/ш/ц hardness, voicing assimilation,
# final devoicing, ъ as separator (ru) vs vowel (bg), щ, digraphs.
_TESTS = [
    # Russian
    ("rus", "весь", "vʲesʲ"), ("rus", "и", "i"), ("rus", "я", "ja"),
    ("rus", "ты", "tɨ"), ("rus", "вода", "voda"), ("rus", "рыба", "rɨba"),
    ("rus", "зуб", "zup"), ("rus", "год", "ɡot"), ("rus", "глаз", "ɡɫas"),
    ("rus", "лёд", "lʲot"), ("rus", "день", "dʲenʲ"), ("rus", "мать", "matʲ"),
    ("rus", "сын", "sɨn"), ("rus", "небо", "nʲebo"), ("rus", "ухо", "uxo"),
    ("rus", "огонь", "oɡonʲ"), ("rus", "рот", "rot"), ("rus", "пять", "pʲatʲ"),
    ("rus", "дерево", "dʲerʲevo"), ("rus", "кровь", "krofʲ"),
    ("rus", "животное", "ʐɨvotnoje"), ("rus", "человек", "t͡ɕeɫovʲek"),
    ("rus", "пепел", "pʲepʲeɫ"), ("rus", "спина", "spʲina"),
    ("rus", "плохой", "pɫoxoj"), ("rus", "водка", "votka"),
    ("rus", "сделать", "zdʲeɫatʲ"), ("rus", "жить", "ʐɨtʲ"),
    ("rus", "щека", "ɕːeka"), ("rus", "конец", "konʲet͡s"),
    # Bulgarian
    ("bul", "и", "i"), ("bul", "вода", "vɔda"), ("bul", "животно", "ʒivɔtnɔ"),
    ("bul", "гръб", "ɡrɤp"), ("bul", "зъб", "zɤp"), ("bul", "лош", "lɔʃ"),
    ("bul", "кора", "kɔra"), ("bul", "око", "ɔkɔ"), ("bul", "ден", "dɛn"),
    ("bul", "куче", "kut͡ʃɛ"), ("bul", "нов", "nɔf"), ("bul", "два", "dva"),
    ("bul", "защото", "zaʃtɔtɔ"), ("bul", "сняг", "snʲak"),
    ("bul", "глава", "ɡlava"), ("bul", "цял", "t͡sʲal"),
    ("bul", "къща", "kɤʃta"), ("bul", "човек", "t͡ʃɔvɛk"),
    # multi-word / synonym handling
    ("rus", "лаять, лай", "ɫajatʲ, ɫaj"),
    # Moksha: coronal-only palatalization, я=æ, э initial, voiceless sonorants,
    # NO final devoicing, glides.
    ("mdf", "сембе", "sʲembe"), ("mdf", "эди", "edʲi"), ("mdf", "ракша", "rakʃa"),
    ("mdf", "кальдяв", "kalʲdʲæv"), ("mdf", "сясьмес", "sʲæsʲmes"),
    ("mdf", "оцю", "ot͡sʲu"), ("mdf", "нармонь", "narmonʲ"), ("mdf", "равжа", "ravʒa"),
    ("mdf", "вер", "ver"), ("mdf", "идь", "idʲ"), ("mdf", "пакарь", "pakarʲ"),
    ("mdf", "пря", "prʲæ"), ("mdf", "кяль", "kælʲ"), ("mdf", "кядьлапш", "kædʲlapʃ"),
    ("mdf", "од", "od"), ("mdf", "кев", "kev"), ("mdf", "сялдаз", "sʲældaz"),
    ("mdf", "якстерь", "jækstʲerʲ"), ("mdf", "шяярь", "ʃæjærʲ"),
    ("mdf", "тюжя", "tʲuʒæ"), ("mdf", "тёга", "tʲoɡa"), ("mdf", "ёрдамс", "jordams"),
    ("mdf", "эрямс", "erʲæms"), ("mdf", "эрьхке", "er̥ʲke"),
    ("mdf", "шалхка", "ʃal̥ka"), ("mdf", "мархта", "mar̥ta"),
    ("mdf", "нюрьхкяня", "nʲur̥ʲkænʲæ"), ("mdf", "видьме", "vidʲme"),
    ("mdf", "пиже", "piʒe"), ("mdf", "ломань", "lomanʲ"), ("mdf", "кода", "koda"),
]


def selftest():
    fails = 0
    for lang, word, want in _TESTS:
        got, _ = to_ipa(word, lang)
        want = unicodedata.normalize("NFC", want)
        got = unicodedata.normalize("NFC", got)
        if got != want:
            fails += 1
            print(f"FAIL {lang} {word!r}: got {got!r}  want {want!r}")
    total = len(_TESTS)
    print(f"cyrillic_g2p self-test: {total - fails}/{total} passed")
    return fails


if __name__ == "__main__":
    import sys
    sys.exit(1 if selftest() else 0)
