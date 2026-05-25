#!/usr/bin/env python3
"""English G2P via the CMU Pronouncing Dictionary (ARPABET -> broad IPA).

The English Swadesh list is gloss-only (no transcription in the corpus), so we
transcribe each English gloss word by lexicon lookup rather than letter rules.
Reads data/external/cmudict.dict (downloaded, gitignored). ARPABET stress digits
are stripped; affricates CH/JH -> ʧ/ʤ (folded to tie-bars by ipa_features); r-colored
ER -> ɝ. First pronunciation per word.

Run `python scripts/cmudict_eng.py` for the self-test (skips if the dict is absent).
"""
import os
import re
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CMU = os.path.join(ROOT, "data", "external", "cmudict.dict")

ARPA = {
    "AA": "ɑ", "AE": "æ", "AH": "ʌ", "AO": "ɔ", "AW": "aʊ", "AY": "aɪ", "B": "b",
    "CH": "ʧ", "D": "d", "DH": "ð", "EH": "ɛ", "ER": "ɝ", "EY": "eɪ", "F": "f",
    "G": "ɡ", "HH": "h", "IH": "ɪ", "IY": "i", "JH": "ʤ", "K": "k", "L": "l",
    "M": "m", "N": "n", "NG": "ŋ", "OW": "oʊ", "OY": "ɔɪ", "P": "p", "R": "ɹ",
    "S": "s", "SH": "ʃ", "T": "t", "TH": "θ", "UH": "ʊ", "UW": "u", "V": "v",
    "W": "w", "Y": "j", "Z": "z", "ZH": "ʒ",
}
_DICT = None


def _load():
    global _DICT
    if _DICT is None:
        _DICT = {}
        with open(CMU, encoding="utf-8") as f:
            for ln in f:
                parts = ln.split()
                if parts and "(" not in parts[0]:        # skip alt-pron entries word(2)
                    _DICT.setdefault(parts[0], parts[1:])
    return _DICT


def _arpa(phones):
    return "".join(ARPA.get(re.sub(r"\d", "", p), "") for p in phones)


def available():
    return os.path.exists(CMU)


def to_ipa(gloss):
    """English gloss -> broad IPA via CMUdict. Returns (ipa, confidence). The gloss
    may carry POS notes / be a phrase -> strip parentheticals, take the first word."""
    w = unicodedata.normalize("NFC", gloss).strip().lower()
    w = re.sub(r"\([^)]*\)", "", w).strip()
    w = (w.split() or [""])[0]
    w = re.sub(r"[^a-z']", "", w)
    ph = _load().get(w)
    return (_arpa(ph), "high") if ph else ("", "")


_TESTS = [("dog", "dɔɡ"), ("water", "wɔtɝ"), ("two", "tu"), ("tooth", "tuθ"),
          ("tongue", "tʌŋ"), ("fish", "fɪʃ"), ("I", "aɪ")]


def selftest():
    if not available():
        print("cmudict_eng self-test: SKIP (no data/external/cmudict.dict)")
        return 0
    fails = 0
    for src, want in _TESTS:
        got = to_ipa(src)[0]
        if unicodedata.normalize("NFC", got) != unicodedata.normalize("NFC", want):
            fails += 1
            print(f"FAIL {src!r}: got {got!r} want {want!r}")
    print(f"cmudict_eng self-test: {len(_TESTS) - fails}/{len(_TESTS)} passed")
    return fails


if __name__ == "__main__":
    import sys
    sys.exit(1 if selftest() else 0)
