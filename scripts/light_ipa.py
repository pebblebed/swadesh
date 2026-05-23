#!/usr/bin/env python3
"""light_ipa cleanup -> broad IPA (Tier 3, first pass).

The 316 light_ipa lists are Latin-based phonetic fieldwork transcriptions that
are ALREADY broad IPA: the ASCII letters (p t k a e i o u m n s ...) are their
own IPA values, plus ~23k genuine IPA symbols (ɸ ɛ ʔ ŋ ː carons, dot-below
retroflexes, ...). They are NOT a foreign orthography needing a G2P; they need
(a) cleanup of non-phonetic noise and (b) the few language-specific letters left
for a later per-source tier -- NOT guessed here.

This pass is deliberately CONSERVATIVE (broad, unverified -> low/medium confidence):
  - Strip non-phonetic noise: '\\' (corruption), '*' (reconstruction mark), '˗',
    '.', '?' (uncertainty), and '-' (morpheme boundary); strip brackets ()[]{}
    keeping their content (optional material -> the fuller form).
  - Split variant separators '/' and '~' into ', '-joined alternants.
  - ñ -> ɲ (the one universally-safe letter: always a palatal nasal).
  - Everything else passes through unchanged (already broad IPA).
  - The genuinely AMBIGUOUS Latin letters c y j x q are LEFT AS-IS and reported
    (metadata/light_ipa_ambiguity.tsv): their IPA value is list/source-specific
    (y = /j/ vs /ɨ/ vs /y/; c = /k/ vs /t͡ʃ/; j = /d͡ʒ/ vs /j/ ...), to be resolved
    per source. A record carrying any of them is marked low confidence.

Run `python scripts/light_ipa.py` for the embedded self-test.
"""
import re
import unicodedata

AMBIG = set("cyjxq")                       # language-specific value; do not guess
_BRACKET = re.compile(r"[()\[\]{}]")
_DROP = "\\*˗.?-"                            # non-phonetic chars to delete
_SEP = re.compile(r"[/~]")                  # variant / alternation separators
_WS = re.compile(r"\s+")


def to_ipa(transcription):
    """Clean a light_ipa transcription to broad IPA. Returns (ipa, ambiguous_set);
    ambiguous_set holds any c/y/j/x/q that remain (deferred to the per-source tier)."""
    t = unicodedata.normalize("NFC", transcription).replace("ñ", "ɲ")
    parts = []
    for alt in _SEP.split(t):
        alt = _BRACKET.sub("", alt)
        for ch in _DROP:
            alt = alt.replace(ch, "")
        alt = _WS.sub(" ", alt).strip()
        if alt and alt not in parts:
            parts.append(alt)
    ipa = ", ".join(parts)
    ambiguous = {c for c in ipa if c in AMBIG}
    return ipa, ambiguous


# ------------------------------- self-test --------------------------------
_TESTS = [
    ("wor~wakka", "wor, wakka", set()),
    ("tambi/tabekobe", "tambi, tabekobe", set()),
    ("poog(l)e", "poogle", set()),
    ("sis(i)", "sisi", set()),
    ("ku\\ani", "kuani", set()),
    ("(ban-)[dum]", "bandum", set()),
    ("no-", "no", set()),
    ("ñam", "ɲam", set()),
    ("ɸuč̣i", "ɸuč̣i", set()),
    ("wose kamui", "wose kamui", set()),
    ("vi˗rar", "virar", set()),
    ("yi-kop", "yikop", {"y"}),
    ("cua", "cua", {"c"}),
    ("da-u ~ da-u", "dau", set()),             # variant split + dedup + hyphen drop
]


def selftest():
    fails = 0
    for src, want_ipa, want_amb in _TESTS:
        ipa, amb = to_ipa(src)
        ipa, want_ipa = unicodedata.normalize("NFC", ipa), unicodedata.normalize("NFC", want_ipa)
        if ipa != want_ipa or amb != want_amb:
            fails += 1
            print(f"FAIL {src!r}: got ({ipa!r},{amb}) want ({want_ipa!r},{want_amb})")
    print(f"light_ipa self-test: {len(_TESTS) - fails}/{len(_TESTS)} passed")
    return fails


if __name__ == "__main__":
    import sys
    sys.exit(1 if selftest() else 0)
