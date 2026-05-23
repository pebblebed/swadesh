#!/usr/bin/env python3
"""Tier 0 of the IPA strategy: classify each list's TRANSCRIPTION SYSTEM.

The corpus is not uniformly IPA. This script reads data/normalized/swadesh.jsonl
and labels every list by what its transcriptions actually contain -- the
prerequisite for any grapheme->IPA conversion (you can't convert what you have
not classified). It writes:
  - data/normalized/transcription_systems.tsv   one row per list (joins to
        list_templates.tsv on `identifier`): scores + a `transcription_system`
  - metadata/transcription_summary.tsv          bucket tallies + the thresholds

The label is derived from per-list character statistics over transcription_norm:

  native:<script>   a non-Latin script dominates (Han, Cyrillic, Arabic, ...).
  ipa_dense         Latin-based and >=25% of entries carry an IPA-only symbol.
  light_ipa         Latin-based, 5-25% of entries carry an IPA-only symbol
                    (phonetic-ish, sparse special symbols).
  americanist       Latin, low IPA signal, but uses caron letters (c v s v z v ...)
                    -- the Americanist/Slavicist phonetic tradition (heuristic;
                    a near-deterministic notation->IPA table is the Tier-1 target).
  plain_ascii       Latin, essentially ASCII only -- bare romanization/orthography.
  latin_diacritic   Latin + orthographic accents/macrons, no IPA signal.
  gloss_only        no transcriptions at all (the English master list).

These are heuristics with explicit, tunable thresholds; the numeric scores are
kept in the report so boundaries can be re-judged without rerunning.
"""
import collections
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSONL = os.path.join(ROOT, "data", "normalized", "swadesh.jsonl")
OUT = os.path.join(ROOT, "data", "normalized", "transcription_systems.tsv")
SUMMARY = os.path.join(ROOT, "metadata", "transcription_summary.tsv")

# --- thresholds (tunable; echoed into the summary for reproducibility) ---
T_IPA_DENSE = 0.25     # >= this fraction of entries with an IPA symbol -> ipa_dense
T_IPA_LIGHT = 0.05     # >= this -> light_ipa
T_NATIVE = 0.30        # >= this fraction of letters in one non-Latin script
T_AMERICANIST = 0.01   # >= this fraction of letters that are caron letters
T_ASCII = 0.01         # < this fraction of non-ASCII chars -> plain_ascii

# IPA-only signal: characters that practical Latin orthography essentially never
# uses. IPA Extensions block (incl. ʔ ə ɛ ɔ ...), plus length/stress marks,
# modifier letters (ʰ ʲ ʷ ...), the tie bar, and the modifier apostrophe.
IPA_SIG = set(range(0x0250, 0x02B0)) | set(range(0x02B0, 0x02B9)) | {
    0x02D0, 0x02D1, 0x02C8, 0x02CC, 0x0361, 0x02BC}
# Caron/hacek letters diagnostic of Americanist/Slavicist phonetic notation.
AMERICANIST = set("čšžǰǯǧǩ")  # č š ž ǰ ǯ ǧ ǩ

NONLATIN = [
    ("Han", 0x4E00, 0x9FFF), ("Han", 0x3400, 0x4DBF), ("Han", 0xF900, 0xFAFF),
    ("Kana", 0x3040, 0x30FF), ("Hangul", 0xAC00, 0xD7A3), ("Hangul", 0x1100, 0x11FF),
    ("Cyrillic", 0x0400, 0x04FF), ("Arabic", 0x0600, 0x06FF),
    ("Devanagari", 0x0900, 0x097F), ("Thai", 0x0E00, 0x0E7F),
    ("Greek", 0x0370, 0x03FF), ("Hebrew", 0x0590, 0x05FF),
]


def nonlatin_script(cp):
    for name, lo, hi in NONLATIN:
        if lo <= cp <= hi:
            return name
    return None


def classify(rows):
    """rows = list of transcription_norm strings (non-empty). Returns
    (system, dom_script, ipa_density, ipa_char_ratio, nonascii_ratio, amer_ratio)."""
    if not rows:
        return ("gloss_only", "", 0.0, 0.0, 0.0, 0.0)
    txt = "".join(rows)
    letters = [c for c in txt if c.isalpha()]
    nL = len(letters) or 1
    nT = len(txt) or 1

    scr = collections.Counter()
    for c in letters:
        s = nonlatin_script(ord(c))
        scr[s or "Latin"] += 1  # IPA-ext counts as Latin-family for dominance
    nonlatin = {k: v for k, v in scr.items() if k != "Latin"}
    dom_script = max(scr, key=scr.get)

    ipa_density = sum(any(ord(c) in IPA_SIG for c in t) for t in rows) / len(rows)
    ipa_char_ratio = sum(1 for c in letters if ord(c) in IPA_SIG) / nL
    nonascii_ratio = sum(1 for c in txt if ord(c) > 127) / nT
    amer_ratio = sum(1 for c in letters if c in AMERICANIST) / nL

    if nonlatin and max(nonlatin.values()) / nL >= T_NATIVE:
        sysname = "native:" + max(nonlatin, key=nonlatin.get)
    elif ipa_density >= T_IPA_DENSE:
        sysname = "ipa_dense"
    elif ipa_density >= T_IPA_LIGHT:
        sysname = "light_ipa"
    elif nonascii_ratio < T_ASCII:
        sysname = "plain_ascii"
    elif amer_ratio >= T_AMERICANIST:
        sysname = "americanist"
    else:
        sysname = "latin_diacritic"
    return (sysname, dom_script, ipa_density, ipa_char_ratio, nonascii_ratio, amer_ratio)


def main():
    rows = collections.defaultdict(list)
    meta = {}
    for line in open(JSONL, encoding="utf-8"):
        r = json.loads(line)
        meta[r["identifier"]] = (r["lang_code"], r["language"] or "")
        if r["transcription_norm"]:
            rows[r["identifier"]].append(r["transcription_norm"])

    out_rows = []
    counts = collections.Counter()
    for ident in sorted(meta):
        sysname, dom, dens, charr, naa, amer = classify(rows.get(ident, []))
        counts[sysname] += 1
        lc, lang = meta[ident]
        out_rows.append((ident, lc, lang, len(rows.get(ident, [])), dom,
                         round(dens, 3), round(charr, 3), round(naa, 3),
                         round(amer, 3), sysname))

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("identifier\tlang_code\tlanguage\tn_transcribed\tdom_script\t"
                "ipa_density\tipa_char_ratio\tnonascii_ratio\tamericanist_ratio\t"
                "transcription_system\n")
        for row in out_rows:
            f.write("\t".join(map(str, row)) + "\n")

    # Group native:* together in the summary ordering, IPA-richest first.
    order = ["ipa_dense", "light_ipa", "americanist", "latin_diacritic",
             "plain_ascii", "gloss_only"]
    natives = sorted(k for k in counts if k.startswith("native:"))
    with open(SUMMARY, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Transcription-system classification of %d lists (Tier 0).\n" % len(out_rows))
        f.write("# thresholds: ipa_dense>=%.2f light_ipa>=%.2f native>=%.2f "
                "americanist>=%.2f plain_ascii<%.2f (nonascii)\n"
                % (T_IPA_DENSE, T_IPA_LIGHT, T_NATIVE, T_AMERICANIST, T_ASCII))
        f.write("transcription_system\tn_lists\n")
        for k in order + natives:
            if counts[k]:
                f.write(f"{k}\t{counts[k]}\n")

    convertible = sum(counts[k] for k in counts if k != "ipa_dense" and k != "gloss_only")
    print(f"lists classified : {len(out_rows)}  -> {OUT}")
    for k in order + natives:
        if counts[k]:
            print(f"  {k:<18}{counts[k]:>5}")
    print(f"\nIPA-ready now      : {counts['ipa_dense']}")
    print(f"need conversion    : {convertible}  (light_ipa + non-IPA + native scripts)")
    print(f"summary -> {SUMMARY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
