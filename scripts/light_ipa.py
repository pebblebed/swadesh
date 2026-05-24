#!/usr/bin/env python3
"""light_ipa cleanup -> broad IPA (Tier 3).

The 316 light_ipa lists are Latin-based phonetic fieldwork transcriptions that
are ALREADY broad IPA: the ASCII letters (p t k a e i o u m n s ...) are their
own IPA values, plus ~23k genuine IPA symbols (ɸ ɛ ʔ ŋ ː carons, dot-below
retroflexes, ...). They are NOT a foreign orthography needing a G2P; they need
(a) cleanup of non-phonetic noise and (b) resolution of the few Latin letters
whose value diverges from their IPA symbol.

PASS 1 (cleanup, conservative):
  - Strip non-phonetic noise: '\\' (corruption), '*' (reconstruction mark), '˗',
    '.', '?' (uncertainty), and '-' (morpheme boundary); strip brackets ()[]{}
    keeping their content (optional material -> the fuller form).
  - Split variant separators '/' and '~' into ', '-joined alternants.
  - ñ -> ɲ (the one universally-safe letter: always a palatal nasal).

PASS 2 / Tier-3b -- the 'y' glide fix (data-grounded):
  In these lists 'y' is OVERWHELMINGLY the palatal glide /j/ (English-convention),
  not the IPA close front rounded vowel /y/. A full-corpus positional scan found
  96% of 'y' tokens sit ADJACENT to a vowel (onset CyV / #yV, intervocalic VyV,
  offglide Vy) -- glide behaviour -- and only ~4% in nucleus position (CyC, Cy#,
  standalone), where 'y' genuinely IS a vowel. So we resolve PER TOKEN, no
  per-language phonology guessed:
    - 'y' adjacent to a vowel        -> 'j'  (the glide; fixes the featurizer's
                                              spurious /y/ vowel, see scripts/vowels.py)
    - 'y' in nucleus position        -> left as-is (a vowel of source-specific
                                              quality /ɨ/~/ɯ/~/y/ -- flagged, not guessed)
  GUARD (set by to_ipa.py): a list that uses 'y' but NEVER 'i' (e.g. `new`) writes
  its high front vowel as 'y'; there resolve_y=False leaves every 'y' untouched.

The remaining genuinely AMBIGUOUS Latin letters c x q are LEFT AS-IS at their IPA
values (palatal stop /c/, velar fricative /x/, uvular stop /q/) but still reported
(metadata/light_ipa_ambiguity.tsv) and keep the record at low confidence: their
source value may diverge (c=/k/~/t͡ʃ/, x=/ʃ/~cluster, q=/ʔ/~/k/) and is not
verifiable without the source's orthography key. 'j' is passed at its IPA glide
value /j/ (the dominant distribution + standard convention; the /d͡ʒ/-convention
lists are a documented, unhandled per-source residual) and does NOT lower
confidence on its own, but its count is reported for transparency.

Run `python scripts/light_ipa.py` for the embedded self-test.
"""
import re
import unicodedata

AMBIG = set("cxq")                          # passed at IPA value, but flagged low-conf
_BRACKET = re.compile(r"[()\[\]{}]")
_DROP = "\\*˗.?-"                            # non-phonetic chars to delete
_SEP = re.compile(r"[/~]")                  # variant / alternation separators
_WS = re.compile(r"\s+")

# Base vowel qualities (NFD base char) used to decide whether a 'y' is a glide
# (adjacent to a vowel) or a nucleus vowel. 'y' itself is excluded -- it is the
# symbol under test. Matches the vowel set in ipa_features.py minus y.
_VOWELS = set("aeiouɨʉɯɪʊeøɘɵɤoəɛœɜɞʌɔæɐɑɒɶ")


def _is_vowel(ch):
    return bool(ch) and unicodedata.normalize("NFD", ch)[0] in _VOWELS


def _adjacent_vowel(s, i, step):
    """Is the nearest *base* char on side `step` (+1/-1) of position i a vowel?
    Skips combining marks and spacing modifiers (length ː, tone, palatalization)
    that cling to a base, so 'aːy' and 'a̋y' read as offglides, not nuclei. A
    word boundary (space/comma) or string edge counts as non-vowel."""
    j = i + step
    while 0 <= j < len(s):
        ch = s[j]
        if unicodedata.combining(ch) or 0x02B0 <= ord(ch) <= 0x02FF:
            j += step
            continue
        if ch in " ,":
            return False
        return _is_vowel(ch)
    return False


def to_ipa(transcription, resolve_y=True):
    """Clean a light_ipa transcription to broad IPA.

    Returns (ipa, ambiguous_set, n_j):
      ambiguous_set -- remaining source-specific letters {c,x,q} and, if any
                       nucleus 'y' survives (or resolve_y is False), 'y'; this set
                       drives low confidence and the per-source ambiguity report.
      n_j           -- count of 'j' (passed at IPA /j/), reported for transparency.
    """
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

    # Tier-3b: resolve the glide 'y' -> 'j'; keep nucleus 'y' as the vowel it is.
    nucleus_y = False
    if "y" in ipa:
        if not resolve_y:
            nucleus_y = True                # whole-list vowel-'y' (no-'i' guard)
        else:
            out = []
            for i, ch in enumerate(ipa):
                if ch == "y":
                    if _adjacent_vowel(ipa, i, 1) or _adjacent_vowel(ipa, i, -1):
                        out.append("j")
                        continue
                    nucleus_y = True        # flanked by consonants/edges -> a vowel
                out.append(ch)
            ipa = "".join(out)

    ambiguous = {c for c in ipa if c in AMBIG}
    if nucleus_y:
        ambiguous.add("y")
    return ipa, ambiguous, ipa.count("j")


# ------------------------------- self-test --------------------------------
# (src, resolve_y, want_ipa, want_ambiguous)
_TESTS = [
    ("wor~wakka", True, "wor, wakka", set()),
    ("tambi/tabekobe", True, "tambi, tabekobe", set()),
    ("poog(l)e", True, "poogle", set()),
    ("sis(i)", True, "sisi", set()),
    ("ku\\ani", True, "kuani", set()),
    ("(ban-)[dum]", True, "bandum", set()),
    ("no-", True, "no", set()),
    ("ñam", True, "ɲam", set()),
    ("ɸuč̣i", True, "ɸuč̣i", set()),
    ("wose kamui", True, "wose kamui", set()),
    ("vi˗rar", True, "virar", set()),
    ("da-u ~ da-u", True, "dau", set()),       # variant split + dedup + hyphen drop
    # --- Tier-3b 'y' glide resolution ---
    ("yi-kop", True, "jikop", set()),          # onset glide #yV -> j
    ("kaya", True, "kaja", set()),             # intervocalic VyV -> j
    ("kay", True, "kaj", set()),               # offglide Vy# -> j
    ("aːy", True, "aːj", set()),               # offglide across length mark -> j
    ("byk", True, "byk", {"y"}),               # nucleus CyC -> stays a vowel (flagged)
    ("y", True, "y", {"y"}),                   # standalone -> vowel
    ("kyaw", True, "kjaw", set()),             # Cy before vowel -> glide j
    ("yaky", True, "jaky", {"y"}),             # mixed: onset y->j, final nucleus y stays
    ("ya", False, "ya", {"y"}),                # no-'i' guard: 'y' left as the vowel
    # --- other ambiguous letters: passed at IPA value, still flagged ---
    ("cua", True, "cua", {"c"}),
    ("qori", True, "qori", {"q"}),
    ("xila", True, "xila", {"x"}),
    ("jaru", True, "jaru", set()),             # 'j' = /j/, not flagged
]


def selftest():
    fails = 0
    for src, ry, want_ipa, want_amb in _TESTS:
        ipa, amb, _ = to_ipa(src, resolve_y=ry)
        ipa, want_ipa = unicodedata.normalize("NFC", ipa), unicodedata.normalize("NFC", want_ipa)
        if ipa != want_ipa or amb != want_amb:
            fails += 1
            print(f"FAIL {src!r} (resolve_y={ry}): got ({ipa!r},{amb}) want ({want_ipa!r},{want_amb})")
    print(f"light_ipa self-test: {len(_TESTS) - fails}/{len(_TESTS)} passed")
    return fails


if __name__ == "__main__":
    import sys
    sys.exit(1 if selftest() else 0)
