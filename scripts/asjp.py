#!/usr/bin/env python3
"""IPA -> ASJP sound-class projection (the uniform coarse layer).

ASJP (Brown, Holman, Wichmann et al.) is a deliberately coarse ASCII alphabet of
41 sound classes -- 7 vowels + 34 consonants -- built for mass language comparison.
It is a LOSSY PROJECTION of phonetics: it discards length, nasalization, tone,
aspiration, ejection, retroflex/dental splits, secondary articulation, syllabicity
and most vowel quality (see notes/asjp.html). We already segmented the corpus into
articulatory features (scripts/ipa_features.py); this module collapses each segment
to its ASJP class by reading those features and DELETING the columns ASJP ignores.

  IPA segment (features)  ──collapse place/manner/voice or height/backness──►  ASJP class

This is ADDITIVE: it imports ipa_features for tokenization but changes nothing in
the existing pipeline. It reads data/normalized/ipa.jsonl and writes a new ASJP
layer; the rich segment-feature tensor stays the decoder's real target (ASJP is
the coverage fallback + external LDND anchor + a coarse backbone, not the output).

Design choices on genuinely-coarse edges (documented + pinned by the self-test):
  - palatal fricatives ç ʝ      -> x   (non-sibilant dorsal fricative bucket)
  - lateral fricative/affricate ɬ ɮ t͡ɬ -> L
  - alveolar affricate t͡s d͡z    -> c   (voicing not distinguished here)
  - voiced uvular/pharyngeal fric ʁ ʕ -> G ; voiceless χ ħ -> X
  - prenasalization / length / tone / 2° articulation -> dropped (ASJP behaviour)
  - segments ipa_features can't identify -> dropped (counted as coverage loss)

Run `python scripts/asjp.py`: the self-test runs FIRST and the build aborts if it
fails, and the build re-checks that every emitted symbol is a real ASJP class.
"""
import collections
import json
import os

import ipa_features  # sibling: reuse segments() + the feature schema

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ND = os.path.join(ROOT, "data", "normalized")
IPA_JSONL = os.path.join(ND, "ipa.jsonl")
OUT = os.path.join(ND, "asjp.jsonl")
SUMMARY = os.path.join(ROOT, "metadata", "asjp_summary.tsv")

# The 41 ASJP classes (7 vowels + 34 consonants). Every emitted char must be here.
ASJP_VOWELS = set("ieE3aou")
ASJP_CONS = set("pbmfv8tdszcnrlSZCjT5kgxNqGX7hLwy!")
ASJP_CLASSES = ASJP_VOWELS | ASJP_CONS

# Segments ipa_features mis-types because NFD splits a precomposed letter: ç/ʝ
# decompose to c/ɟ + cedilla and read as palatal STOPS, but they are palatal
# FRICATIVES. Override on the recomposed segment string (a featurizer gap noted in
# TODO; fixed here locally so the projection is right without regenerating features).
SEG_OVERRIDE = {"ç": "x", "ʝ": "x"}

# Vowels collapse on (height, backness); rounding, length, nasalization, tone dropped.
VREG = {
    ("close", "front"): "i", ("close", "central"): "i", ("close", "back"): "u",
    ("near-close", "front"): "i", ("near-close", "central"): "i", ("near-close", "back"): "u",
    ("close-mid", "front"): "e", ("close-mid", "central"): "3", ("close-mid", "back"): "o",
    ("mid", "front"): "e", ("mid", "central"): "3", ("mid", "back"): "o",
    ("open-mid", "front"): "E", ("open-mid", "central"): "3", ("open-mid", "back"): "o",
    ("near-open", "front"): "E", ("near-open", "central"): "3", ("near-open", "back"): "a",
    ("open", "front"): "a", ("open", "central"): "a", ("open", "back"): "a",
}


def cons_asjp(seg):
    """ASJP class for a consonant segment (by manner/place/voice; modifiers ignored)."""
    place = seg.get("place", "")
    manner = seg.get("manner", "")
    vd = seg.get("voice") == "voiced"

    if "lateral" in manner:                       # laterals: l vs L; fric/affr/click handled
        if "approximant" in manner:
            return "L" if place in ("palatal", "velar") else "l"
        if "click" in manner:
            return "!"
        return "L"                                # lateral fricative ɬ ɮ / lateral affricate t͡ɬ
    if manner == "click":
        return "!"
    if manner in ("plosive", "implosive"):
        if place in ("bilabial", "labiodental"):
            return "b" if vd else "p"
        if place in ("alveolar", "dental", "retroflex", "labial-alveolar"):
            return "d" if vd else "t"
        if place == "palatal":
            return "T"
        if place in ("velar", "labial-velar", "labial-palatal"):
            return "g" if vd else "k"
        if place == "uvular":
            return "G" if vd else "q"
        if place in ("glottal", "epiglottal", "pharyngeal"):
            return "7"
        return None
    if manner == "nasal":
        if place in ("bilabial", "labiodental"):
            return "m"
        if place in ("alveolar", "dental", "retroflex"):
            return "n"
        if place == "palatal":
            return "5"
        if place in ("velar", "uvular", "labial-velar"):
            return "N"
        return "n"
    if manner in ("trill", "tap"):
        return "r"
    if manner == "fricative":
        if place in ("bilabial", "labiodental"):
            return "v" if vd else "f"
        if place == "dental":
            return "8"
        if place == "alveolar":
            return "z" if vd else "s"
        if place in ("postalveolar", "retroflex", "alveolo-palatal"):
            return "Z" if vd else "S"
        if place in ("palatal", "velar"):
            return "x"
        if place in ("uvular", "pharyngeal"):
            return "G" if vd else "X"
        if place in ("glottal", "epiglottal"):
            return "h"
        return None
    if manner == "affricate":
        if place == "alveolar":
            return "c"
        if place in ("postalveolar", "retroflex", "alveolo-palatal", "palatal", "dental"):
            return "j" if vd else "C"
        if place in ("velar", "uvular"):
            return "g" if vd else "k"              # rare kx-type -> stop bucket
        return None
    if manner == "approximant":
        if place == "palatal":
            return "y"
        if place in ("labial-velar", "velar", "labial-palatal"):
            return "w"
        if place == "labiodental":
            return "v"
        if place in ("alveolar", "retroflex", "dental"):
            return "r"
        return None
    return None


def seg_to_asjp(seg):
    """ASJP class for one segment dict, or None if it has no ASJP class (dropped)."""
    ov = SEG_OVERRIDE.get(seg.get("seg"))
    if ov:
        return ov
    t = seg.get("type")
    if t == "vowel":
        return VREG.get((seg.get("height"), seg.get("backness")))
    if t == "consonant":
        return cons_asjp(seg)
    return None                                   # unknown / unmappable -> dropped


def ipa_to_asjp(ipa):
    """Project an IPA string to ASJP. Comma-separated alternants are kept as
    space-separated words; everything else collapses per segment."""
    parts = []
    for part in ipa.split(","):
        w = "".join(a for a in (seg_to_asjp(s) for s in ipa_features.segments(part)) if a)
        if w:
            parts.append(w)
    return " ".join(parts)


# --------------------------------- build ----------------------------------

def build():
    cls_freq = collections.Counter()
    dropped = collections.Counter()               # unmapped segment -> count (coverage loss)
    bad = collections.Counter()                    # emitted non-ASJP char (must stay empty!)
    n_rec = n_seg = n_drop = n_empty = 0
    with open(IPA_JSONL, encoding="utf-8") as fin, \
         open(OUT, "w", encoding="utf-8", newline="\n") as fout:
        for line in fin:
            r = json.loads(line)
            if not r["ipa"]:
                continue
            words = []
            for part in r["ipa"].split(","):
                chars = []
                for seg in ipa_features.segments(part):
                    n_seg += 1
                    a = seg_to_asjp(seg)
                    if a is None:
                        n_drop += 1
                        dropped[seg.get("seg", "?")] += 1
                        continue
                    if a not in ASJP_CLASSES:
                        bad[a] += 1
                    cls_freq[a] += 1
                    chars.append(a)
                if chars:
                    words.append("".join(chars))
            asjp = " ".join(words)
            n_rec += 1
            if not asjp:
                n_empty += 1
            fout.write(json.dumps({"identifier": r["identifier"], "lang_code": r["lang_code"],
                                   "gloss": r["gloss"],
                                   "canonical_gloss": r.get("canonical_gloss", ""),
                                   "ipa": r["ipa"], "asjp": asjp}, ensure_ascii=False) + "\n")

    cov = 100 * (n_seg - n_drop) / n_seg if n_seg else 0
    with open(SUMMARY, "w", encoding="utf-8", newline="\n") as f:
        f.write("# IPA -> ASJP projection coverage (scripts/asjp.py).\n")
        f.write(f"records_projected\t{n_rec}\n")
        f.write(f"records_empty_asjp\t{n_empty}\n")
        f.write(f"segments\t{n_seg}\n")
        f.write(f"segments_mapped\t{n_seg - n_drop}\n")
        f.write(f"segments_dropped\t{n_drop}\n")
        f.write(f"coverage_pct\t{cov:.2f}\n")
        f.write(f"distinct_classes_used\t{len(cls_freq)}\n")
        f.write(f"invalid_chars_emitted\t{sum(bad.values())}\n")
        f.write("\n# ASJP class frequency (should be a subset of the 41 classes)\n")
        f.write("class\tn\n")
        for c, n in cls_freq.most_common():
            f.write(f"{c}\t{n}\n")
        f.write("\n# Top dropped segments (no ASJP class -> coverage loss; audit)\n")
        f.write("segment\tn\n")
        for s, n in dropped.most_common(30):
            f.write(f"{s}\t{n}\n")

    print(f"records projected : {n_rec}  -> {OUT}")
    print(f"segments          : {n_seg}  ({n_seg - n_drop} mapped, {n_drop} dropped"
          f" = {cov:.2f}% coverage)")
    print(f"classes used      : {len(cls_freq)} / 41")
    print(f"summary           : {SUMMARY}")
    if bad:
        print(f"!! INVALID non-ASJP chars emitted: {dict(bad)} -- mapping bug, fix before use")
        return 1
    if n_empty:
        print(f"note: {n_empty} records projected to empty ASJP (all segments unmappable)")
    return 0


# ------------------------------- self-test --------------------------------
# (ipa, expected_asjp). Covers every class, the lossy collapses, affricates,
# presub digraphs, multi-word/alternant handling, and unknown-drop.
_TESTS = [
    # plosives / nasals / glottal
    ("p", "p"), ("b", "b"), ("t", "t"), ("d", "d"), ("k", "k"), ("ɡ", "g"),
    ("q", "q"), ("ɢ", "G"), ("ʔ", "7"), ("m", "m"), ("n", "n"), ("ŋ", "N"),
    ("ɲ", "5"), ("ɴ", "N"), ("c", "T"), ("ɟ", "T"),          # palatal stops -> T (note ASCII c)
    # fricatives
    ("f", "f"), ("v", "v"), ("θ", "8"), ("ð", "8"), ("s", "s"), ("z", "z"),
    ("ʃ", "S"), ("ʒ", "Z"), ("ʂ", "S"), ("ʐ", "Z"), ("x", "x"), ("ɣ", "x"),
    ("χ", "X"), ("ʁ", "G"), ("ħ", "X"), ("ʕ", "G"), ("h", "h"), ("ɦ", "h"),
    ("ç", "x"), ("ʝ", "x"),                                   # palatal fric -> x (documented)
    # affricates
    ("t͡s", "c"), ("d͡z", "c"), ("t͡ʃ", "C"), ("d͡ʒ", "j"), ("t͡ɕ", "C"), ("t͡ɬ", "L"),
    # sonorants / liquids / glides
    ("r", "r"), ("ɾ", "r"), ("ʀ", "r"), ("l", "l"), ("ʎ", "L"), ("ɬ", "L"),
    ("j", "y"), ("w", "w"), ("ɥ", "w"), ("ɻ", "r"), ("ʋ", "v"),
    # implosives / retroflex -> base class (implosion / retroflexion dropped)
    ("ɓ", "b"), ("ɗ", "d"), ("ʈ", "t"), ("ɖ", "d"),
    # vowels (rounding/centrality collapsed to 7 classes)
    ("i", "i"), ("e", "e"), ("a", "a"), ("o", "o"), ("u", "u"),
    ("y", "i"), ("ø", "e"), ("ɨ", "i"), ("ɯ", "u"), ("ə", "3"), ("ɛ", "E"),
    ("œ", "E"), ("æ", "E"), ("ɔ", "o"), ("ʌ", "o"), ("ɤ", "o"), ("ɑ", "a"),
    ("ɒ", "a"), ("ɐ", "3"), ("ʊ", "u"), ("ɪ", "i"),
    # the lossy collapses (the part we must not silently break)
    ("aː", "a"), ("ã", "a"), ("á", "a"), ("ɔ̃ː", "o"),        # length/nasal/tone dropped
    ("kʰ", "k"), ("tʲ", "t"), ("kʷ", "k"), ("n̩", "n"),       # aspiration/2°/syllabic dropped
    ("ⁿd", "d"), ("ᵐb", "b"),                                # prenasalization dropped
    # presub digraphs (Americanist/Slavicist)
    ("š", "S"), ("č", "C"), ("ž", "Z"), ("ɫ", "l"),
    # words, alternants, unknown-drop
    ("kahiki", "kahiki"), ("motu", "motu"), ("kaja", "kaya"), ("t͡ʃiʔ", "Ci7"),
    ("kaja, motu", "kaya motu"), ("ßa", "a"),
]


def selftest():
    fails = 0
    for ipa, want in _TESTS:
        got = ipa_to_asjp(ipa)
        if got != want:
            fails += 1
            print(f"FAIL {ipa!r}: got {got!r}  want {want!r}")
    # invariant: every gold output is composed only of real ASJP classes
    for _, want in _TESTS:
        for ch in want.replace(" ", ""):
            if ch not in ASJP_CLASSES:
                fails += 1
                print(f"FAIL gold {want!r}: {ch!r} is not an ASJP class")
    print(f"asjp self-test: {len(_TESTS) - fails}/{len(_TESTS)} passed")
    return fails


if __name__ == "__main__":
    import sys
    if selftest():
        sys.exit(1)
    sys.exit(build())
