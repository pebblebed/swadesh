#!/usr/bin/env python3
"""Classify every Swadesh list by which extension 'blocks' it carries.

Turns the qualitative cluster analysis (see TODO.md FINDINGS) into a hard
taxonomy. Reads data/normalized/swadesh.jsonl and writes:
  - data/normalized/list_templates.tsv   one row per list: per-block counts,
                                          present-flags, and a primary category
  - metadata/template_summary.tsv        corpus-level tallies

The extension BLOCKS below were identified empirically: each is a set of
NON-canonical glosses that co-occur tightly (high Jaccard) across the corpus.
A block is "present" in a list when the list carries at least `min_hits` of its
members -- enough to conclude the list used that page of the questionnaire,
robust to a few missing items.
"""
import collections
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSONL = os.path.join(ROOT, "data", "normalized", "swadesh.jsonl")
OUT = os.path.join(ROOT, "data", "normalized", "list_templates.tsv")
SUMMARY = os.path.join(ROOT, "metadata", "template_summary.tsv")

# block name -> (min_hits, [member glosses]).  Members are non-canonical concepts
# (after alias resolution); see scripts/normalize.py for the gloss keys.
BLOCKS = {
    # Regional add-on: Australia + New Guinea endemics. The diagnostic cluster.
    "sahul_fauna": (2, ["emu", "kangaroo", "wallaby", "cassowary", "crocodile", "woomera"]),
    # Extended body-part page (roughly doubles the canonical inventory).
    "body_part": (3, ["arm", "shoulder", "finger", "elbow", "forehead", "chin",
                       "chest", "navel", "thigh", "face", "throat", "lip", "calf",
                       "nape", "ankle", "cheek", "jaw", "wrist", "heel"]),
    # Kinship & age grades Swadesh omitted (he kept only parents/spouses).
    "kinship_age": (2, ["brother", "sister", "boy", "girl", "son", "daughter"]),
    # Deictic time words beyond canonical day/night/year.
    "time_deixis": (2, ["tomorrow", "yesterday", "morning", "today"]),
    # Weather pair (thunder<->lightning, Jaccard 0.78).
    "weather": (2, ["thunder", "lightning"]),
    # Grammatical: number (dual) + inclusive/exclusive. Often a real feature of
    # the language, not just the questionnaire -> reported as its own dimension.
    "dual_clusivity": (2, ["we (incl.)", "we (excl.)", "we two", "we two (incl.)",
                           "we two (excl.)", "you two", "they two"]),
}

STUB_MAX = 10  # lists with fewer kept entries than this are too small to classify


def categorize(present, n_entries):
    """Assign one primary category from the set of present blocks.

    The 'questionnaire' blocks (body_part/kinship_age/time_deixis/weather) signal
    the worldwide extended wordlist; sahul_fauna pins it to the Sahul region.
    dual_clusivity is treated as an orthogonal grammatical flag, not a category.
    """
    questionnaire = present & {"body_part", "kinship_age", "time_deixis", "weather"}
    if "sahul_fauna" in present:
        return "sahul_extended"
    if len(questionnaire) >= 2:
        return "extended_worldwide"
    if questionnaire:
        return "lightly_extended"
    if n_entries < STUB_MAX:
        return "stub"
    return "core_swadesh"


def main():
    extras = collections.defaultdict(set)   # ident -> set(non-canonical glosses)
    n_canon = collections.Counter()         # ident -> # distinct canonical concepts
    n_entries = collections.Counter()       # ident -> # records (kept entries)
    meta = {}                               # ident -> (lang_code, language, kind)
    for line in open(JSONL, encoding="utf-8"):
        r = json.loads(line)
        ident = r["identifier"]
        meta[ident] = (r["lang_code"], r["language"], r["kind"])
        n_entries[ident] += 1
        if r["in_canonical"]:
            n_canon[ident] += 1
        else:
            extras[ident].add(r["canonical_gloss"])

    members = {b: set(m) for b, (_, m) in BLOCKS.items()}
    minhit = {b: mh for b, (mh, _) in BLOCKS.items()}

    rows = []
    cat_count = collections.Counter()
    block_count = collections.Counter()
    nblocks_hist = collections.Counter()
    dual_by_cat = collections.Counter()

    for ident in sorted(meta):
        ex = extras.get(ident, set())
        counts = {b: len(ex & members[b]) for b in BLOCKS}
        present = {b for b in BLOCKS if counts[b] >= minhit[b]}
        cat = categorize(present, n_entries[ident])
        # questionnaire-block count excludes the orthogonal dual_clusivity flag
        nq = len(present - {"dual_clusivity"})
        cat_count[cat] += 1
        nblocks_hist[nq] += 1
        for b in present:
            block_count[b] += 1
        if "dual_clusivity" in present:
            dual_by_cat[cat] += 1
        lang_code, language, kind = meta[ident]
        rows.append((ident, lang_code, language or "", kind, n_entries[ident],
                     n_canon[ident], len(ex),
                     counts["sahul_fauna"], counts["body_part"], counts["kinship_age"],
                     counts["time_deixis"], counts["weather"], counts["dual_clusivity"],
                     int("dual_clusivity" in present), cat))

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("identifier\tlang_code\tlanguage\tkind\tn_entries\tn_canonical\t"
                "n_extra\tsahul_fauna\tbody_part\tkinship_age\ttime_deixis\t"
                "weather\tdual_clusivity\thas_dual\tcategory\n")
        for row in rows:
            f.write("\t".join(map(str, row)) + "\n")

    order = ["sahul_extended", "extended_worldwide", "lightly_extended",
             "core_swadesh", "stub"]
    with open(SUMMARY, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Swadesh list template taxonomy -- counts over %d lists\n" % len(rows))
        f.write("category\tn_lists\tw/_dual_clusivity\n")
        for c in order:
            f.write(f"{c}\t{cat_count[c]}\t{dual_by_cat[c]}\n")
        f.write("\nblock\tn_lists_present\tmin_hits\tn_members\n")
        for b, (mh, m) in BLOCKS.items():
            f.write(f"{b}\t{block_count[b]}\t{mh}\t{len(m)}\n")
        f.write("\nquestionnaire_blocks_present\tn_lists\n")
        for k in sorted(nblocks_hist):
            f.write(f"{k}\t{nblocks_hist[k]}\n")

    print(f"lists classified : {len(rows)}  -> {OUT}")
    print("category breakdown:")
    for c in order:
        d = dual_by_cat[c]
        print(f"  {c:<20}{cat_count[c]:>5}   ({d} also carry dual/clusivity)")
    print("block prevalence (lists where the block is present):")
    for b in BLOCKS:
        print(f"  {b:<16}{block_count[b]:>5}")
    print(f"summary -> {SUMMARY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
