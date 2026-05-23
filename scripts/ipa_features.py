#!/usr/bin/env python3
"""Structured IPA features: tokenize the IPA layer into segments + phonetic features.

The endgame of the IPA strategy. Reads data/normalized/ipa.jsonl (the best-effort
`ipa` field, populated on 633 lists / ~150k records by to_ipa.py) and turns each
transcription into a list of phonetic SEGMENTS, each with articulatory features --
"voiceless glottal fricative" instead of a raw `h`.

Tokenization (per transcription):
  1. NFC, then a small PRESUB folds caron/digraph consonants to canonical IPA
     (č->t͡ʃ š->ʃ ž->ʒ ǯ/ǰ->d͡ʒ ť->c ď->ɟ ň->ɲ ľ->ʎ; ƛ->t͡ɬ; ɫ->lˠ; ʧ/ʤ/ʦ/ʣ).
  2. NFD, so precomposed accented vowels split into base + combining mark
     (á->a+◌́, ã->a+◌̃, ā->a+◌̄, ṭ->t+◌̣ ...). This collapses the 239 raw base
     letters to ~70 real IPA bases; the accents become features.
  3. Greedy segmentation: a base letter, optionally a tie-bar-joined second base
     (affricate t͡ʃ / co-articulated k͡p), then trailing combining marks and
     spacing modifiers (ː ʰ ʲ ʷ ˤ ...). Stress marks ˈ ˌ and spaces/`,` are breaks.

Features:
  - consonant: voice, place, manner (+ modifiers: aspirated/palatalized/...,
    length, nasalized, syllabic).
  - vowel: height, backness, rounding (+ length, nasalized, tone, modifiers).
  - `desc` is a readable gloss built from the features.
  - Symbols with no feature entry -> type "unknown" (flagged in the inventory),
    e.g. archiphoneme capitals (N V T), residual non-IPA (ß, stray э).

Outputs (run `python scripts/ipa_features.py`):
  - data/normalized/ipa_features.jsonl     per-record segments (gitignored, regen)
  - metadata/ipa_segment_inventory.tsv     distinct segments + features + freq (TRACKED)
  - metadata/ipa_features_summary.tsv       coverage + top unknown segments (TRACKED)
Self-test runs first; the build aborts if it fails.
"""
import collections
import json
import os
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ND = os.path.join(ROOT, "data", "normalized")
IPA_JSONL = os.path.join(ND, "ipa.jsonl")
OUT = os.path.join(ND, "ipa_features.jsonl")
INVENTORY = os.path.join(ROOT, "metadata", "ipa_segment_inventory.tsv")
SUMMARY = os.path.join(ROOT, "metadata", "ipa_features_summary.tsv")

TIE = "͡"   # combining double inverted breve (affricate tie bar)

# Fold non-decomposable letters to canonical IPA before NFD. Caron consonants are
# the Americanist/Slavicist tradition; the tesh/dezh digraph chars and ƛ/ɫ too.
PRESUB = {
    "č": "t͡ʃ", "ǯ": "d͡ʒ", "ǰ": "d͡ʒ", "š": "ʃ", "ž": "ʒ", "ǧ": "d͡ʒ",
    "ť": "c", "ď": "ɟ", "ň": "ɲ", "ľ": "ʎ", "ʧ": "t͡ʃ", "ʤ": "d͡ʒ",
    "ʦ": "t͡s", "ʣ": "d͡z", "ƛ": "t͡ɬ", "ɫ": "lˠ", "g": "ɡ",
}

# Consonants: base -> (voice, place, manner).
CONS = {
    "p": ("voiceless", "bilabial", "plosive"), "b": ("voiced", "bilabial", "plosive"),
    "t": ("voiceless", "alveolar", "plosive"), "d": ("voiced", "alveolar", "plosive"),
    "ʈ": ("voiceless", "retroflex", "plosive"), "ɖ": ("voiced", "retroflex", "plosive"),
    "c": ("voiceless", "palatal", "plosive"), "ɟ": ("voiced", "palatal", "plosive"),
    "k": ("voiceless", "velar", "plosive"), "ɡ": ("voiced", "velar", "plosive"),
    "q": ("voiceless", "uvular", "plosive"), "ɢ": ("voiced", "uvular", "plosive"),
    "ʠ": ("voiceless", "uvular", "plosive"),          # q-with-hook (ejective sense lost)
    "ʔ": ("voiceless", "glottal", "plosive"),
    "ʡ": ("voiceless", "epiglottal", "plosive"),
    "m": ("voiced", "bilabial", "nasal"), "ɱ": ("voiced", "labiodental", "nasal"),
    "n": ("voiced", "alveolar", "nasal"), "ɳ": ("voiced", "retroflex", "nasal"),
    "ɲ": ("voiced", "palatal", "nasal"), "ŋ": ("voiced", "velar", "nasal"),
    "ɴ": ("voiced", "uvular", "nasal"),
    "ʙ": ("voiced", "bilabial", "trill"), "r": ("voiced", "alveolar", "trill"),
    "ʀ": ("voiced", "uvular", "trill"),
    "ɾ": ("voiced", "alveolar", "tap"), "ɽ": ("voiced", "retroflex", "tap"),
    "ⱱ": ("voiced", "labiodental", "tap"),
    "ɸ": ("voiceless", "bilabial", "fricative"), "β": ("voiced", "bilabial", "fricative"),
    "f": ("voiceless", "labiodental", "fricative"), "v": ("voiced", "labiodental", "fricative"),
    "θ": ("voiceless", "dental", "fricative"), "ð": ("voiced", "dental", "fricative"),
    "s": ("voiceless", "alveolar", "fricative"), "z": ("voiced", "alveolar", "fricative"),
    "ʃ": ("voiceless", "postalveolar", "fricative"), "ʒ": ("voiced", "postalveolar", "fricative"),
    "ʂ": ("voiceless", "retroflex", "fricative"), "ʐ": ("voiced", "retroflex", "fricative"),
    "ɕ": ("voiceless", "alveolo-palatal", "fricative"), "ʑ": ("voiced", "alveolo-palatal", "fricative"),
    "ç": ("voiceless", "palatal", "fricative"), "ʝ": ("voiced", "palatal", "fricative"),
    "x": ("voiceless", "velar", "fricative"), "ɣ": ("voiced", "velar", "fricative"),
    "χ": ("voiceless", "uvular", "fricative"), "ʁ": ("voiced", "uvular", "fricative"),
    "ħ": ("voiceless", "pharyngeal", "fricative"), "ʕ": ("voiced", "pharyngeal", "fricative"),
    "ʢ": ("voiced", "epiglottal", "fricative"),
    "h": ("voiceless", "glottal", "fricative"), "ɦ": ("voiced", "glottal", "fricative"),
    "ɬ": ("voiceless", "alveolar", "lateral fricative"), "ɮ": ("voiced", "alveolar", "lateral fricative"),
    "ʋ": ("voiced", "labiodental", "approximant"), "ɹ": ("voiced", "alveolar", "approximant"),
    "ɻ": ("voiced", "retroflex", "approximant"), "j": ("voiced", "palatal", "approximant"),
    "ɰ": ("voiced", "velar", "approximant"), "w": ("voiced", "labial-velar", "approximant"),
    "ɥ": ("voiced", "labial-palatal", "approximant"),
    "l": ("voiced", "alveolar", "lateral approximant"), "ɭ": ("voiced", "retroflex", "lateral approximant"),
    "ʎ": ("voiced", "palatal", "lateral approximant"), "ʟ": ("voiced", "velar", "lateral approximant"),
    "ɓ": ("voiced", "bilabial", "implosive"), "ɗ": ("voiced", "alveolar", "implosive"),
    "ʄ": ("voiced", "palatal", "implosive"), "ɠ": ("voiced", "velar", "implosive"),
    "ʛ": ("voiced", "uvular", "implosive"),
    "ʘ": ("voiceless", "bilabial", "click"), "ǀ": ("voiceless", "dental", "click"),
    "ǃ": ("voiceless", "postalveolar", "click"), "ǂ": ("voiceless", "palatal", "click"),
    "ǁ": ("voiceless", "alveolar", "lateral click"),
}

# Vowels: base -> (height, backness, rounding).
VOW = {
    "i": ("close", "front", "unrounded"), "y": ("close", "front", "rounded"),
    "ɨ": ("close", "central", "unrounded"), "ʉ": ("close", "central", "rounded"),
    "ɯ": ("close", "back", "unrounded"), "u": ("close", "back", "rounded"),
    "ɪ": ("near-close", "front", "unrounded"), "ʏ": ("near-close", "front", "rounded"),
    "ʊ": ("near-close", "back", "rounded"),
    "e": ("close-mid", "front", "unrounded"), "ø": ("close-mid", "front", "rounded"),
    "ɘ": ("close-mid", "central", "unrounded"), "ɵ": ("close-mid", "central", "rounded"),
    "ɤ": ("close-mid", "back", "unrounded"), "o": ("close-mid", "back", "rounded"),
    "ə": ("mid", "central", "unrounded"),
    "ɛ": ("open-mid", "front", "unrounded"), "œ": ("open-mid", "front", "rounded"),
    "ɜ": ("open-mid", "central", "unrounded"), "ɞ": ("open-mid", "central", "rounded"),
    "ʌ": ("open-mid", "back", "unrounded"), "ɔ": ("open-mid", "back", "rounded"),
    "æ": ("near-open", "front", "unrounded"), "ɐ": ("near-open", "central", "unrounded"),
    "a": ("open", "front", "unrounded"), "ɶ": ("open", "front", "rounded"),
    "ɑ": ("open", "back", "unrounded"), "ɒ": ("open", "back", "rounded"),
}

# Combining marks (U+0300..036F): cp -> (field, value). 'mod' appends to modifiers.
COMB = {
    0x0300: ("tone", "low"), 0x0301: ("tone", "high"), 0x0302: ("tone", "falling"),
    0x030C: ("tone", "rising"), 0x0304: ("length", "long"), 0x0306: ("mod", "extra-short"),
    0x0303: ("nasalized", True), 0x0308: ("mod", "centralized"), 0x030A: ("mod", "ring"),
    0x0325: ("voice", "voiceless"), 0x030D: ("syllabic", True), 0x0329: ("syllabic", True),
    0x032A: ("place", "dental"), 0x0330: ("mod", "creaky"), 0x0324: ("mod", "breathy"),
    0x031D: ("mod", "raised"), 0x031E: ("mod", "lowered"), 0x0320: ("mod", "retracted"),
    0x0318: ("mod", "advanced"), 0x0339: ("mod", "more-rounded"), 0x031C: ("mod", "less-rounded"),
    0x0334: ("mod", "velarized"), 0x031F: ("mod", "advanced"), 0x0353: ("mod", "lowered"),
}
DOT_BELOW = 0x0323            # retroflex on a coronal consonant; else 'retracted'
CORONAL = {"alveolar", "dental", "postalveolar"}

# Spacing modifier letters (U+02B0..02FF) + superscript-n: cp -> (field, value).
MODS = {
    0x02D0: ("length", "long"), 0x02D1: ("length", "half-long"),
    0x02B0: ("mod", "aspirated"), 0x02B1: ("mod", "breathy-aspirated"),
    0x02B2: ("mod", "palatalized"), 0x02B7: ("mod", "labialized"),
    0x02E0: ("mod", "velarized"), 0x02E4: ("mod", "pharyngealized"),
    0x02BC: ("mod", "ejective"), 0x02DE: ("mod", "rhotacized"),
    0x02C0: ("mod", "glottalized"),
    0x02B9: ("mod", "palatalized"), 0x02D2: ("mod", "more-rounded"),
    0x02D3: ("mod", "less-rounded"),
}
# Superscript nasals mark PREnasalization of the FOLLOWING consonant (ⁿd, ᵐb),
# so they attach forward, not as a trailing mark of the previous segment.
PRENASAL = {"ⁿ", "ᵐ", "ᵑ", "ᶬ"}
# Non-phonetic characters: dropped wherever they occur (boundaries, brackets,
# stress, the data-quality junk noted in TODO: stray \  ( ) [ ] tone-digits ¢ ...).
SKIP = set(" \t\r\n.,;/|()[]{}-~?!=&+*\\¢´`¯µ·•↓↑°@#%<>\"")
SKIP |= set("0123456789")
SKIP |= {"ˈ", "ˌ", "'", "’", "‘", "ʹ", "ʺ"}          # stress / apostrophes
SKIP |= {"˗", "˖", "˔", "˕", "‖"}                     # modifier minus/plus/tacks (used as seps)


def _is_comb(c):
    return 0x0300 <= ord(c) <= 0x036F


def _is_mod(c):
    cp = ord(c)
    return 0x02B0 <= cp <= 0x02FF or cp == 0x207F


def _is_base(c):
    return c.isalpha() and not _is_mod(c) and not _is_comb(c)


def _combine_place(p1, p2):
    if {p1, p2} == {"bilabial", "velar"}:
        return "labial-velar"
    if {p1, p2} == {"bilabial", "alveolar"}:
        return "labial-alveolar"
    return f"{p1}-{p2}"


def _feature(base, second):
    """Core features (no diacritics yet) for a base, optionally tie-bar-joined to
    `second`. Returns a feature dict with 'type' consonant/vowel/unknown."""
    if second is not None:
        b1, b2 = CONS.get(base), CONS.get(second)
        if b2 and "fricative" in b2[2]:                  # plosive + fricative -> affricate
            manner = "lateral affricate" if "lateral" in b2[2] else "affricate"
            voice = (b1 or b2)[0]
            return {"type": "consonant", "voice": voice, "place": b2[1], "manner": manner}
        if b1 and b2 and b1[2] == b2[2]:                 # co-articulated (k͡p, m͡ŋ)
            return {"type": "consonant", "voice": b1[0],
                    "place": _combine_place(b1[1], b2[1]), "manner": b1[2]}
        if b1:
            return {"type": "consonant", "voice": b1[0], "place": b1[1], "manner": b1[2]}
        return {"type": "unknown"}
    if base in CONS:
        v, p, m = CONS[base]
        return {"type": "consonant", "voice": v, "place": p, "manner": m}
    if base in VOW:
        h, bk, rd = VOW[base]
        return {"type": "vowel", "height": h, "backness": bk, "rounding": rd}
    return {"type": "unknown"}


def _apply_diacritics(feat, marks):
    """Fold combining marks + spacing modifiers (list of chars) into feat."""
    mods = []
    for c in marks:
        if c == ":":                              # ASCII colon used as length mark
            feat["length"] = "long"
            continue
        cp = ord(c)
        if cp == DOT_BELOW:
            if feat.get("type") == "consonant" and feat.get("place") in CORONAL:
                feat["place"] = "retroflex"
            else:
                mods.append("retracted")
            continue
        spec = COMB.get(cp) or MODS.get(cp)
        if spec is None:
            mods.append(f"U+{cp:04X}")
            continue
        field, val = spec
        if field == "mod":
            mods.append(val)
        else:
            feat[field] = val
    if mods:
        feat["modifiers"] = mods
    return feat


def describe(feat):
    """Readable articulatory gloss (tone is a field, not part of the gloss)."""
    if feat.get("type") == "unknown":
        return "unknown"
    mods = feat.get("modifiers", [])
    length = ["long"] if feat.get("length") == "long" else (
        ["half-long"] if feat.get("length") == "half-long" else [])
    nas = ["nasalized"] if feat.get("nasalized") else []
    if feat["type"] == "consonant":
        syl = ["syllabic"] if feat.get("syllabic") else []
        parts = length + [feat["voice"]] + nas + syl + mods + [feat["place"], feat["manner"]]
    else:
        parts = length + nas + mods + [feat["height"], feat["backness"],
                                       feat["rounding"], "vowel"]
    return " ".join(parts)


def segments(ipa):
    """Tokenize an IPA string into segment dicts (each with `seg`, features, `desc`)."""
    s = unicodedata.normalize("NFC", ipa)
    for k, v in PRESUB.items():
        if k in s:
            s = s.replace(k, v)
    s = unicodedata.normalize("NFD", s)
    out, i, n, pending = [], 0, len(s), []
    while i < n:
        c = s[i]
        if c in SKIP:
            i += 1
            continue
        if c in PRENASAL:                               # attaches to NEXT consonant
            pending.append("prenasalized")
            i += 1
            continue
        if not _is_base(c):
            if _is_mod(c) or _is_comb(c) or c == ":":   # orphan diacritic -> drop
                i += 1
            else:                                       # real non-IPA symbol -> flag
                out.append({"seg": c, "type": "unknown", "desc": "unknown"})
                i += 1
            continue
        chars, base, second = [c], c, None
        i += 1
        if i + 1 < n and s[i] == TIE and _is_base(s[i + 1]):
            chars += [s[i], s[i + 1]]
            second = s[i + 1]
            i += 2
        marks = []
        while (i < n and s[i] not in SKIP and s[i] not in PRENASAL
               and (_is_comb(s[i]) or _is_mod(s[i]) or s[i] == ":")):
            chars.append(s[i])
            marks.append(s[i])
            i += 1
        feat = _apply_diacritics(_feature(base, second), marks)
        if pending:                                     # prefix any prenasalization
            feat["modifiers"] = pending + feat.get("modifiers", [])
            pending = []
        seg = unicodedata.normalize("NFC", "".join(chars))
        rec = {"seg": seg}
        rec.update(feat)
        rec["desc"] = describe(feat)
        out.append(rec)
    return out


# --------------------------------- build ----------------------------------

def build():
    inv = collections.defaultdict(lambda: {"n": 0, "lists": set(), "feat": None})
    n_seg = n_unknown = n_rec = 0
    with open(IPA_JSONL, encoding="utf-8") as fin, \
         open(OUT, "w", encoding="utf-8", newline="\n") as fout:
        for line in fin:
            r = json.loads(line)
            if not r["ipa"]:
                continue
            segs = segments(r["ipa"])
            n_rec += 1
            for sg in segs:
                n_seg += 1
                key = sg["seg"]
                e = inv[key]
                e["n"] += 1
                e["lists"].add(r["identifier"])
                if e["feat"] is None:
                    e["feat"] = sg
                if sg["type"] == "unknown":
                    n_unknown += 1
            fout.write(json.dumps({"identifier": r["identifier"],
                                   "lang_code": r["lang_code"], "gloss": r["gloss"],
                                   "ipa": r["ipa"], "segments": segs},
                                  ensure_ascii=False) + "\n")

    with open(INVENTORY, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Distinct IPA segments across the corpus IPA layer, with features.\n")
        f.write("segment\ttype\tdescription\ttone\tn_occurrences\tn_lists\n")
        for key in sorted(inv, key=lambda k: -inv[k]["n"]):
            e = inv[key]
            ft = e["feat"]
            f.write(f"{key}\t{ft['type']}\t{ft.get('desc', '')}\t"
                    f"{ft.get('tone', '')}\t{e['n']}\t{len(e['lists'])}\n")

    known = {k: v for k, v in inv.items() if v["feat"]["type"] != "unknown"}
    unknown = {k: v for k, v in inv.items() if v["feat"]["type"] == "unknown"}
    with open(SUMMARY, "w", encoding="utf-8", newline="\n") as f:
        f.write("# IPA feature coverage over the IPA layer.\n")
        f.write(f"records_with_ipa\t{n_rec}\n")
        f.write(f"total_segments\t{n_seg}\n")
        f.write(f"segment_occurrences_known\t{n_seg - n_unknown}\n")
        f.write(f"segment_occurrences_unknown\t{n_unknown}\n")
        f.write(f"coverage_pct\t{100 * (n_seg - n_unknown) / n_seg:.2f}\n")
        f.write(f"distinct_segments\t{len(inv)}\n")
        f.write(f"distinct_known\t{len(known)}\n")
        f.write(f"distinct_unknown\t{len(unknown)}\n")
        f.write("\n# Top unmapped segments (candidates for the feature table / cleanup)\n")
        f.write("segment\tn_occurrences\tn_lists\n")
        for key in sorted(unknown, key=lambda k: -unknown[k]["n"])[:40]:
            e = unknown[key]
            f.write(f"{key}\t{e['n']}\t{len(e['lists'])}\n")

    print(f"records featurized : {n_rec}  -> {OUT}")
    print(f"segments           : {n_seg}  ({n_seg - n_unknown} known, {n_unknown} unknown"
          f" = {100 * (n_seg - n_unknown) / n_seg:.2f}% coverage)")
    print(f"distinct segments  : {len(inv)}  ({len(known)} known, {len(unknown)} unknown)")
    print(f"inventory -> {INVENTORY}")
    print(f"summary   -> {SUMMARY}")
    return 0


# ------------------------------- self-test --------------------------------
_TESTS = [
    ("h", "voiceless glottal fricative"),
    ("ʔ", "voiceless glottal plosive"),
    ("ŋ", "voiced velar nasal"),
    ("ɸ", "voiceless bilabial fricative"),
    ("ɬ", "voiceless alveolar lateral fricative"),
    ("t͡ʃ", "voiceless postalveolar affricate"),
    ("d͡z", "voiced alveolar affricate"),
    ("t͡ɬ", "voiceless alveolar lateral affricate"),
    ("kʰ", "voiceless aspirated velar plosive"),
    ("tʲ", "voiceless palatalized alveolar plosive"),
    ("n̩", "voiced syllabic alveolar nasal"),
    ("ṭ", "voiceless retroflex plosive"),       # t + dot below
    ("š", "voiceless postalveolar fricative"),  # presub -> ʃ
    ("č", "voiceless postalveolar affricate"),  # presub -> t͡ʃ
    ("ɫ", "voiced velarized alveolar lateral approximant"),  # presub -> lˠ
    ("a", "open front unrounded vowel"),
    ("aː", "long open front unrounded vowel"),
    ("y", "close front rounded vowel"),
    ("ə", "mid central unrounded vowel"),
    ("õ", "nasalized close-mid back rounded vowel"),
    ("ɔ̃ː", "long nasalized open-mid back rounded vowel"),
    ("ⁿd", "voiced prenasalized alveolar plosive"),     # ⁿ attaches forward
]


def selftest():
    fails = 0
    for ipa, want in _TESTS:
        segs = segments(ipa)
        got = segs[0]["desc"] if len(segs) == 1 else f"<{len(segs)} segs>"
        if got != want:
            fails += 1
            print(f"FAIL {ipa!r}: got {got!r}  want {want!r}")
    # a couple of field checks
    a_acute = segments("á")[0]
    if a_acute.get("tone") != "high":
        fails += 1
        print(f"FAIL 'á' tone: {a_acute.get('tone')!r} want 'high'")
    print(f"ipa_features self-test: {len(_TESTS) + 1 - fails}/{len(_TESTS) + 1} passed")
    return fails


if __name__ == "__main__":
    import sys
    if selftest():
        sys.exit(1)
    sys.exit(build())
