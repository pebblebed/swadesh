#!/usr/bin/env python3
"""Practical-orthography -> broad IPA (Tier 3a).

The deferred_latin bucket (272 lists) splits three ways. The big, coherent slice
-- ~230 lists of Papuan / Austronesian / African / Americas FIELDWORK languages --
is written in a practical (SIL / Indonesian-style) orthography that is broad-phonemic
already: almost every letter is its own IPA value, with just a couple of multigraph
conventions on top. This module converts that slice. The other two slices are routed
ELSEWHERE by to_ipa.py and are NOT handled here:
  - national/deep orthographies (French, German, Dutch, Danish, Hindi, Armenian,
    Hungarian, Turkish, Vietnamese, ...) -> stay deferred_latin (need per-language G2P);
  - Mayan (K'iche', Kaqchikel, Q'eqchi', Mam, Chuj, Jakalteko, Poqomam, Ch'orti',
    Achi) -> stay deferred_latin (distinct convention: x=/ʃ/, j=/x/, tz=/t͡s/, '=ejective,
    ·=length; a dedicated Mayan G2P is future work, see TODO).

This is the SAME philosophy as light_ipa (cleanup + the 'y' glide fix), PLUS the two
near-universal practical multigraphs, verified against the corpus (Agob, Tok Pisin,
Baruya, Sahu, Eipomek, ...):
  - ng -> ŋ   (velar nasal; the single most standard practical convention. A real
               /n.g/ or /ŋɡ/ is rare and usually written ŋg / n'g; 'ngg' -> 'ŋg' falls
               out correctly. Lists that mix ŋ and 'ng' both mean /ŋ/, so merging is right.)
  - ny -> ɲ   (palatal nasal; Indonesian/SIL convention)
applied BEFORE the 'y' glide fix so 'ny' is consumed first. Prenasalized mb/nd/nj are
left as written (broad). The genuinely source-specific letters c x q are passed at
their IPA value (palatal stop / velar fricative / uvular stop) but flagged low-conf
and reported; 'j' is passed at IPA /j/. The '\\' corruption (a source-specific glottal
/ ejective marker) is DROPPED as noise (as in light_ipa) -- '\\'-heavy lists are flagged
for a future per-source pass rather than guessed.

Broad + unverified -> low/medium confidence, like light_ipa. Run
`python scripts/practical_g2p.py` for the embedded self-test.
"""
import unicodedata

import light_ipa  # sibling module: reuse clean() + resolve_glide_y() + AMBIG


def expand_digraphs(s):
    """The two safe practical multigraphs. ng -> ŋ then ny -> ɲ (order-independent
    here; neither rewrites into the other's trigger)."""
    return s.replace("ng", "ŋ").replace("ny", "ɲ")


def to_ipa(transcription, resolve_y=True):
    """Practical orthography -> broad IPA. Returns (ipa, ambiguous_set, n_j) with
    the same contract as light_ipa.to_ipa (ambiguous = {c,x,q} + nucleus 'y')."""
    ipa = light_ipa.clean(transcription)
    ipa = expand_digraphs(ipa)
    ipa, nucleus_y = light_ipa.resolve_glide_y(ipa, resolve_y)
    ambiguous = {c for c in ipa if c in light_ipa.AMBIG}
    if nucleus_y:
        ambiguous.add("y")
    return ipa, ambiguous, ipa.count("j")


# ------------------------------- self-test --------------------------------
# (src, resolve_y, want_ipa, want_ambiguous)
_TESTS = [
    # ng -> ŋ (incl. word-internal, final, and the ngg/ngk fall-through)
    ("darang", True, "daraŋ", set()),
    ("tang", True, "taŋ", set()),
    ("manga", True, "maŋa", set()),            # /maŋa/
    ("tonggol", True, "toŋgol", set()),        # ngg -> ŋg (prenasal/cluster kept)
    ("baŋirise", True, "baŋirise", set()),     # already-ŋ list passes through
    # ny -> ɲ
    ("banyo", True, "baɲo", set()),
    ("betinye", True, "betiɲe", set()),
    ("nyila", True, "ɲila", set()),
    # 'y' glide fix still applies to non-digraph y (after ng/ny consumed)
    ("yam", True, "jam", set()),
    ("kaya", True, "kaja", set()),
    ("nyamuk", True, "ɲamuk", set()),          # ny consumed; no stray y
    ("wanpela", True, "wanpela", set()),       # n+p, no digraph
    # prenasalized + already-IPA pass through; cleanup still runs
    ("dumbrel", True, "dumbrel", set()),       # mb kept
    ("eraβa", True, "eraβa", set()),           # β passes
    ("ku\\ani", True, "kuani", set()),         # '\' dropped as noise
    ("poar(i)", True, "poari", set()),         # brackets stripped
    # source-specific letters: passed at IPA value, flagged (except j)
    ("coi", True, "coi", {"c"}),
    ("qori", True, "qori", {"q"}),
    ("jaru", True, "jaru", set()),             # j -> /j/, not flagged
    # nucleus 'y' as a vowel stays + flagged; no-'i' guard
    ("byk", True, "byk", {"y"}),
    ("nyk", False, "ɲk", set()),               # ny->ɲ; no leftover y
]


def selftest():
    fails = 0
    for src, ry, want_ipa, want_amb in _TESTS:
        ipa, amb, _ = to_ipa(src, resolve_y=ry)
        ipa, want_ipa = unicodedata.normalize("NFC", ipa), unicodedata.normalize("NFC", want_ipa)
        if ipa != want_ipa or amb != want_amb:
            fails += 1
            print(f"FAIL {src!r} (resolve_y={ry}): got ({ipa!r},{amb}) want ({want_ipa!r},{want_amb})")
    print(f"practical_g2p self-test: {len(_TESTS) - fails}/{len(_TESTS)} passed")
    return fails


if __name__ == "__main__":
    import sys
    sys.exit(1 if selftest() else 0)
