#!/usr/bin/env python3
"""Mandarin pinyin -> IPA (Tier 2, the deterministic half of the cmn pipeline).

The cmn (Mandarin) Swadesh list is bare Hanzi with no romanization, so the
lexical step -- Hanzi -> pinyin -- is a curated dictionary (metadata/
cmn_hanzi_pinyin.tsv). THIS module is the mechanical, testable second step:
pinyin (with tone digits) -> broad-phonemic IPA, including the pinyin orthographic
quirks.

Per syllable: strip the trailing tone digit (1-4, 5/neutral); undo the spelling
conventions (zero-initial y/w -> i/u glide; j/q/x + u -> ü; iu->iou ui->uei
un->uen; b/p/m/f + o -> uo); split the initial; map initial + final to IPA; the
apical "-i" after zh/ch/sh/r -> ɻ̩ and after z/c/s -> ɹ̩. Tone -> Chao tone
letters (1=˥ 2=˧˥ 3=˨˩˦ 4=˥˩, neutral unmarked), matching the Thai handler.

Run `python scripts/pinyin_g2p.py` for the embedded self-test.
"""
import unicodedata

TIE = "͡"
SYL = "̩"   # combining vertical line below (syllabic)

INIT = {
    "b": "p", "p": "pʰ", "m": "m", "f": "f",
    "d": "t", "t": "tʰ", "n": "n", "l": "l",
    "g": "k", "k": "kʰ", "h": "x",
    "j": "t" + TIE + "ɕ", "q": "t" + TIE + "ɕʰ", "x": "ɕ",
    "zh": "ʈ" + TIE + "ʂ", "ch": "ʈ" + TIE + "ʂʰ", "sh": "ʂ", "r": "ʐ",
    "z": "t" + TIE + "s", "c": "t" + TIE + "sʰ", "s": "s",
}
FINALS = {
    "a": "a", "o": "o", "e": "ɤ", "ê": "ɛ", "er": "ɚ",
    "ai": "ai", "ei": "ei", "ao": "au", "ou": "ou",
    "an": "an", "en": "ən", "ang": "aŋ", "eng": "əŋ", "ong": "ʊŋ",
    "i": "i", "ia": "ja", "ie": "je", "iao": "jau", "iou": "jou",
    "ian": "jɛn", "in": "in", "iang": "jaŋ", "ing": "iŋ", "iong": "jʊŋ",
    "u": "u", "ua": "wa", "uo": "wo", "uai": "wai", "uei": "wei",
    "uan": "wan", "uen": "wən", "uang": "waŋ", "ueng": "wəŋ",
    "ü": "y", "üe": "ɥe", "üan": "ɥɛn", "ün": "yn",
}
TONE = {"1": "˥", "2": "˧˥", "3": "˨˩˦", "4": "˥˩", "5": "", "": ""}


def _canon(syl):
    """pinyin syllable (no tone) -> (initial, final) in canonical form."""
    if syl.startswith("yu"):
        syl = "ü" + syl[2:]                       # yu/yue/yuan/yun -> ü...
    elif syl.startswith("y"):
        syl = "i" + syl[1:]
        if syl.startswith("ii"):
            syl = syl[1:]                          # yi -> i, yin -> in
    elif syl.startswith("w"):
        syl = "u" + syl[1:]
        if syl.startswith("uu"):
            syl = syl[1:]                          # wu -> u
    init = ""
    for k in ("zh", "ch", "sh"):
        if syl.startswith(k):
            init = k
            break
    if not init and syl[:1] in "bpmfdtnlgkhjqxrzcs":
        init = syl[0]
    final = syl[len(init):]
    if init in ("j", "q", "x") and final.startswith("u"):
        final = "ü" + final[1:]                    # ju -> jü
    if init:                                        # abbreviated finals need an initial
        final = {"iu": "iou", "ui": "uei", "un": "uen"}.get(final, final)
    if init in ("b", "p", "m", "f") and final == "o":
        final = "uo"                               # bo -> [pwo]
    return init, final


def _syl_to_ipa(syl):
    tone = ""
    if syl and syl[-1] in "12345":
        tone, syl = syl[-1], syl[:-1]
    init, final = _canon(syl.lower())
    residual = set()
    if final == "i" and init in ("zh", "ch", "sh", "r"):
        fip = "ɻ" + SYL
    elif final == "i" and init in ("z", "c", "s"):
        fip = "ɹ" + SYL
    elif final in FINALS:
        fip = FINALS[final]
    else:
        residual.add(final or syl)
        fip = final
    return INIT.get(init, "") + fip + TONE[tone], residual


def to_ipa(pinyin):
    """Convert a space-separated pinyin transcription (tone digits) to IPA.
    Syllables of a word are joined without spaces. Returns (ipa, residual_set)."""
    residual, sylls = set(), []
    for syl in unicodedata.normalize("NFC", pinyin).split():
        ipa, res = _syl_to_ipa(syl)
        residual |= res
        sylls.append(ipa)
    return "".join(sylls), residual


# ------------------------------- self-test --------------------------------
_TESTS = [
    ("hui1", "xwei˥"), ("quan2", "t͡ɕʰɥɛn˧˥"), ("bu4", "pu˥˩"),
    ("shu4", "ʂu˥˩"), ("pi2", "pʰi˧˥"), ("chi1", "ʈ͡ʂʰɻ̩˥"),
    ("si3", "sɹ̩˨˩˦"), ("zhi1", "ʈ͡ʂɻ̩˥"), ("ren2", "ʐən˧˥"),
    ("xue4", "ɕɥe˥˩"), ("wo3", "wo˨˩˦"), ("yi1", "i˥"),
    ("er4", "ɚ˥˩"), ("lü4", "ly˥˩"), ("nü3", "ny˨˩˦"),
    ("niao3", "njau˨˩˦"), ("shuo1", "ʂwo˥"), ("huo3", "xwo˨˩˦"),
    ("you2", "jou˧˥"), ("yu2", "y˧˥"), ("shei2", "ʂei˧˥"),
    ("shen2", "ʂən˧˥"), ("me5", "mɤ"), ("tou5", "tʰou"),
    ("hong2", "xʊŋ˧˥"), ("jiao3", "t͡ɕjau˨˩˦"), ("gu3 tou5", "ku˨˩˦tʰou"),
]


def selftest():
    fails = 0
    for src, want in _TESTS:
        got, _ = to_ipa(src)
        got, want = unicodedata.normalize("NFC", got), unicodedata.normalize("NFC", want)
        if got != want:
            fails += 1
            print(f"FAIL {src!r}: got {got!r}  want {want!r}")
    print(f"pinyin_g2p self-test: {len(_TESTS) - fails}/{len(_TESTS)} passed")
    return fails


if __name__ == "__main__":
    import sys
    sys.exit(1 if selftest() else 0)
