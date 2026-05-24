#!/usr/bin/env python3
"""Per-language VOWEL inventories from the IPA feature layer.

First model-ready artifact for the vocalic-change model (see TODO 'MODELING
DIRECTION'): the model conditions on (language, concept) and decodes a phonetic
form, so it needs each language's vowel system. This reads data/normalized/
ipa_features.jsonl, and for every list tallies the vowel QUALITIES it uses (the
base vowel; length / nasalization / tone counted separately). It doubles as an
IPA-quality audit -- anomalous inventories surface featurizer or data problems.

CAVEAT (documented, not silently fixed): in the light_ipa lists the Latin letter
'y' is an UNRESOLVED ambiguous symbol (often /j/ or /ɨ/, not the vowel /y/; see
metadata/light_ipa_ambiguity.tsv). It is featurized as the close front rounded
vowel and so inflates 'y' counts in those lists. Flagged in the summary; resolve
in the per-source Tier-3b pass before trusting 'y' as a vowel there.

Outputs (TRACKED):
  - metadata/vowel_inventories.tsv   one row per list: inventory + suprasegmental counts
  - metadata/vowel_summary.tsv       corpus vowel frequency, inventory-size distribution,
                                     suprasegmental rates, flagged outliers
"""
import collections
import csv
import json
import os
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEAT = os.path.join(ROOT, "data", "normalized", "ipa_features.jsonl")
SYSTEMS = os.path.join(ROOT, "data", "normalized", "transcription_systems.tsv")
INV = os.path.join(ROOT, "metadata", "vowel_inventories.tsv")
SUMMARY = os.path.join(ROOT, "metadata", "vowel_summary.tsv")

# Canonical IPA vowel bases (matches the VOW table in ipa_features.py).
VOWELS = set("iyɨʉɯuɪʏʊeøɘɵɤoəɛœɜɞʌɔæɐaɶɑɒ")
# Outlier thresholds for the audit (tunable).
HI, LO = 12, 3


def base_vowel(seg):
    """The base vowel quality of a vowel segment (strip length/nasal/tone/mods)."""
    for ch in unicodedata.normalize("NFD", seg):
        if ch in VOWELS:
            return ch
    return None


def load_meta():
    meta = {}
    for r in csv.DictReader(open(SYSTEMS, encoding="utf-8"), delimiter="\t"):
        meta[r["identifier"]] = (r["lang_code"], r["language"], r["transcription_system"])
    return meta


def main():
    meta = load_meta()
    # per list: vowel-quality counter + suprasegmental tallies + token/record counts
    inv = collections.defaultdict(lambda: {
        "q": collections.Counter(), "tok": 0, "long": 0, "nas": 0, "tone": 0, "rec": 0})
    corpus_q = collections.Counter()          # quality -> total tokens
    corpus_lists = collections.defaultdict(set)  # quality -> set of lists
    tot_tok = tot_long = tot_nas = tot_tone = 0
    flagged_base = collections.Counter()      # vowel segs with no recognised base

    for line in open(FEAT, encoding="utf-8"):
        r = json.loads(line)
        ident = r["identifier"]
        e = inv[ident]
        e["rec"] += 1
        for s in r["segments"]:
            if s.get("type") != "vowel":
                continue
            q = base_vowel(s["seg"])
            if q is None:
                flagged_base[s["seg"]] += 1
                continue
            e["q"][q] += 1
            e["tok"] += 1
            corpus_q[q] += 1
            corpus_lists[q].add(ident)
            tot_tok += 1
            if s.get("length") == "long":
                e["long"] += 1; tot_long += 1
            if s.get("nasalized"):
                e["nas"] += 1; tot_nas += 1
            if s.get("tone"):
                e["tone"] += 1; tot_tone += 1

    # ---- per-list inventory file ----
    with open(INV, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Per-list vowel inventory (base qualities) from ipa_features.jsonl.\n")
        f.write("identifier\tlang_code\tlanguage\tsystem\tn_records\tn_vowel_tokens\t"
                "n_qualities\tpct_long\tpct_nasal\tpct_tone\tinventory\n")
        for ident in sorted(inv):
            e = inv[ident]
            lc, lang, sysn = meta.get(ident, ("", "", ""))
            tok = e["tok"] or 1
            invstr = " ".join(f"{q}:{n}" for q, n in e["q"].most_common())
            f.write(f"{ident}\t{lc}\t{lang}\t{sysn}\t{e['rec']}\t{e['tok']}\t{len(e['q'])}\t"
                    f"{100*e['long']//tok}\t{100*e['nas']//tok}\t{100*e['tone']//tok}\t{invstr}\n")

    # ---- corpus summary ----
    sizes = collections.Counter(len(inv[i]["q"]) for i in inv if inv[i]["tok"])
    big = sorted(((i, len(inv[i]["q"])) for i in inv if len(inv[i]["q"]) > HI),
                 key=lambda x: -x[1])
    small = sorted(((i, len(inv[i]["q"])) for i in inv if 0 < len(inv[i]["q"]) < LO),
                   key=lambda x: x[1])
    tt = tot_tok or 1
    with open(SUMMARY, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Corpus vowel summary from ipa_features.jsonl.\n")
        f.write(f"lists_with_vowels\t{sum(1 for i in inv if inv[i]['tok'])}\n")
        f.write(f"vowel_tokens\t{tot_tok}\n")
        f.write(f"distinct_qualities\t{len(corpus_q)}\n")
        f.write(f"pct_long\t{100*tot_long/tt:.2f}\n")
        f.write(f"pct_nasal\t{100*tot_nas/tt:.2f}\n")
        f.write(f"pct_tone\t{100*tot_tone/tt:.2f}\n")

        f.write("\n# Vowel quality frequency (token count, #lists attesting)\n")
        f.write("vowel\tn_tokens\tn_lists\n")
        for q, n in corpus_q.most_common():
            f.write(f"{q}\t{n}\t{len(corpus_lists[q])}\n")

        f.write("\n# Inventory-size distribution (n distinct vowel qualities -> n lists)\n")
        f.write("n_qualities\tn_lists\n")
        for k in sorted(sizes):
            f.write(f"{k}\t{sizes[k]}\n")

        f.write(f"\n# Outlier inventories: > {HI} qualities (audit; 'y' may be the "
                "ambiguous light_ipa letter)\n")
        f.write("identifier\tlang_code\tlanguage\tn_qualities\n")
        for ident, k in big:
            lc, lang, _ = meta.get(ident, ("", "", ""))
            f.write(f"{ident}\t{lc}\t{lang}\t{k}\n")

        f.write(f"\n# Outlier inventories: < {LO} qualities (audit; tiny / odd lists)\n")
        f.write("identifier\tlang_code\tlanguage\tn_qualities\n")
        for ident, k in small:
            lc, lang, _ = meta.get(ident, ("", "", ""))
            f.write(f"{ident}\t{lc}\t{lang}\t{k}\n")

        if flagged_base:
            f.write("\n# vowel-typed segments with no recognised base (featurizer audit)\n")
            f.write("segment\tn\n")
            for s, n in flagged_base.most_common(20):
                f.write(f"{s}\t{n}\n")

    print(f"lists with vowels  : {sum(1 for i in inv if inv[i]['tok'])}  -> {INV}")
    print(f"vowel tokens       : {tot_tok}  ({len(corpus_q)} distinct qualities)")
    print(f"suprasegmental     : {100*tot_long/tt:.1f}% long, "
          f"{100*tot_nas/tt:.1f}% nasal, {100*tot_tone/tt:.1f}% tone")
    print(f"inventory outliers : {len(big)} >{HI} qualities, {len(small)} <{LO}")
    if flagged_base:
        print(f"featurizer audit   : {sum(flagged_base.values())} vowel segs with no base "
              f"-> see {SUMMARY}")
    print(f"summary            : {SUMMARY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
