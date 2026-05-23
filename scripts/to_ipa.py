#!/usr/bin/env python3
"""Assemble the IPA layer of the corpus (extensible across conversion tiers).

Reads data/normalized/swadesh.jsonl + data/normalized/transcription_systems.tsv
and produces, per record, a best-effort `ipa` plus `ipa_method` / `ipa_confidence`.
Currently implemented:
  - native_ipa   : ipa_dense lists pass through unchanged (605 lists).      [Tier 0 give]
  - americanist  : caron notation -> IPA via metadata/americanist_ipa_map.tsv.  [Tier 1]
  - slavic_g2p   : Czech/Slovak native orthography -> IPA via scripts/slavic_g2p.py
                   (rule-based G2P: palatalization, diphthongs, voicing assim.).  [Tier 1]
  - greek_g2p    : Modern Greek spelling -> IPA via scripts/native_g2p.py.        [Tier 2]
  - kana_g2p     : Japanese hiragana -> IPA via scripts/native_g2p.py.            [Tier 2]
  - cyrillic_g2p : Russian/Bulgarian Cyrillic -> IPA via scripts/cyrillic_g2p.py
                   (broad phonemic; Moksha deferred).                             [Tier 2]
  - romanization : the Latin/IPA romanization line that arb (Arabic, already IPA)
                   and tha (Thai, +Chao tones) carry, via scripts/romanize.py.    [Tier 2]
  - cmn          : Mandarin Hanzi -> pinyin (curated metadata/cmn_hanzi_pinyin.tsv)
                   -> IPA via scripts/pinyin_g2p.py.                               [Tier 2]
  - deferred_*   : recognized but not yet converted (other native scripts,
                   low-resource Latin) -> ipa left empty for later tiers.

Outputs:
  - data/normalized/ipa.jsonl                 the IPA layer (gitignored, regenerable)
  - data/normalized/ipa_americanist_review.tsv  raw->ipa for every converted
        Americanist entry, with any residual (unconverted) symbols flagged (TRACKED)
  - data/normalized/ipa_slavic_review.tsv      raw->ipa for every Czech/Slovak
        entry, residuals flagged (TRACKED)
  - metadata/ipa_conversion_summary.tsv       method/confidence tallies (TRACKED)
"""
import collections
import csv
import json
import os

import cyrillic_g2p  # sibling modules in scripts/ (on sys.path when run as a script)
import native_g2p
import pinyin_g2p
import romanize
import slavic_g2p

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ND = os.path.join(ROOT, "data", "normalized")
JSONL = os.path.join(ND, "swadesh.jsonl")
SYSTEMS = os.path.join(ND, "transcription_systems.tsv")
MAP = os.path.join(ROOT, "metadata", "americanist_ipa_map.tsv")
CMN_MAP = os.path.join(ROOT, "metadata", "cmn_hanzi_pinyin.tsv")
OUT = os.path.join(ND, "ipa.jsonl")
REVIEW = os.path.join(ND, "ipa_americanist_review.tsv")
SLAVIC_REVIEW = os.path.join(ND, "ipa_slavic_review.tsv")
NATIVE_REVIEW = os.path.join(ND, "ipa_native_review.tsv")
CYR_REVIEW = os.path.join(ND, "ipa_cyrillic_review.tsv")
ROM_REVIEW = os.path.join(ND, "ipa_romanization_review.tsv")
CMN_REVIEW = os.path.join(ND, "ipa_cmn_review.tsv")
SUMMARY = os.path.join(ROOT, "metadata", "ipa_conversion_summary.tsv")

SLAVIC = {"ces", "slk"}  # lang_codes whose carons are native orthography, not Americanist
# native-script systems with a Tier-2 G2P -> (script arg for native_g2p, method name)
NATIVE_G2P = {"native:Greek": ("Greek", "greek_g2p"),
              "native:Kana": ("Kana", "kana_g2p")}
# Cyrillic-script lang_codes with a Tier-2 G2P (cyrillic_g2p). mdf (Moksha,
# Uralic) is deferred -- needs language-specific rules + separate verification.
CYRILLIC_G2P = {"rus", "bul"}
# Native-script lists that carry a Latin/IPA ROMANIZATION line per gloss; we
# convert that line (sidestepping the script). lang_code -> converter.
ROMANIZE = {"tha": romanize.thai_to_ipa, "arb": romanize.arabic_to_ipa}


def is_cyrillic(t):
    """True if Cyrillic letters dominate the string (its native line, not a
    romanized synonym line interleaved in the same list)."""
    cyr = sum(1 for c in t if 0x0400 <= ord(c) <= 0x04FF)
    other = sum(1 for c in t if c.isalpha() and not 0x0400 <= ord(c) <= 0x04FF)
    return cyr > other


def is_latin_line(t):
    """True if the record is the Latin/IPA romanization line (not the native
    script). IPA-extension letters count as Latin-family."""
    lat = sum(1 for c in t if c.isalpha() and (ord(c) < 0x0300 or 0x0250 <= ord(c) <= 0x02AF))
    non = sum(1 for c in t if c.isalpha()
              and not (ord(c) < 0x0300 or 0x0250 <= ord(c) <= 0x02AF))
    return lat > non

# Codepoints that are legitimately IPA (so they don't count as conversion residue):
# IPA Extensions + Spacing Modifier Letters + Combining Diacritics + tie bar,
# plus a few valid IPA symbols outside those blocks.
# Valid IPA symbols that live OUTSIDE the IPA-Extensions block (borrowed from
# Latin-1 / Greek): voiced/voiceless dental fricatives, palatal fricative, beta,
# chi, front rounded/low vowels, eng, superscript-n, tie bar.
_IPA_EXTRA = set("ðθçβχøæŋⁿ͡")


def is_ipa_ok(c):
    cp = ord(c)
    if cp < 0x80 and c != "\\":      # plain ASCII (IPA bases p,t,k,a,e,...) except '\'
        return True
    if 0x0250 <= cp <= 0x02FF:       # IPA ext + modifier letters (ː ˈ ʰ ˗ ...)
        return True
    if 0x0300 <= cp <= 0x036F:       # combining diacritics (nasal, dental, voiceless...)
        return True
    return c in _IPA_EXTRA


def load_map():
    m = {}
    with open(MAP, encoding="utf-8") as f:
        for ln in f:
            if not ln.strip() or ln.lstrip().startswith("#"):
                continue
            parts = ln.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[0] != "source":
                m[ord(parts[0])] = parts[1]
    return m


def load_cmn():
    """Hanzi -> pinyin from the curated cmn dict (keyed on transcription_norm)."""
    with open(CMN_MAP, encoding="utf-8") as f:
        lines = [ln for ln in f if not ln.lstrip().startswith("#")]
    d = {}
    for row in csv.DictReader(lines, delimiter="\t"):
        if row.get("hanzi") and row.get("pinyin"):
            d[row["hanzi"].strip()] = row["pinyin"].strip()
    return d


def main():
    sysrow = {r["identifier"]: r for r in
              csv.DictReader(open(SYSTEMS, encoding="utf-8"), delimiter="\t")}
    amer_map = load_map()
    cmn_map = load_cmn()

    methods = collections.Counter()
    conf_count = collections.Counter()
    review = []
    slavic_review = []
    native_review = []
    cyrillic_review = []
    romanization_review = []
    cmn_review = []
    residual_by_list = collections.defaultdict(collections.Counter)

    with open(JSONL, encoding="utf-8") as fin, \
         open(OUT, "w", encoding="utf-8", newline="\n") as fout:
        for line in fin:
            r = json.loads(line)
            ident = r["identifier"]
            system = sysrow.get(ident, {}).get("transcription_system", "unknown")
            t = r["transcription_norm"]
            ipa, method, conf = "", "unconverted", ""

            if not t:
                method = "empty"
            elif system == "ipa_dense":
                ipa, method, conf = t, "native_ipa", "high"
            elif system == "americanist" and r["lang_code"] in SLAVIC:
                ipa, residual_set = slavic_g2p.to_ipa(t, r["lang_code"])
                residual = sorted(residual_set)
                conf = "high" if not residual else "medium"
                method = "slavic_g2p"
                for c in residual:
                    residual_by_list[ident][c] += 1
                slavic_review.append((ident, r["lang_code"], r["gloss"], t, ipa,
                                      "".join(residual)))
            elif system == "americanist":
                ipa = t.translate(amer_map)
                residual = sorted({c for c in ipa if not is_ipa_ok(c)})
                conf = "high" if not residual else "medium"
                method = "americanist"
                for c in residual:
                    residual_by_list[ident][c] += 1
                review.append((ident, r["lang_code"], r["gloss"], t, ipa,
                               "".join(residual)))
            elif system in NATIVE_G2P:
                script, method = NATIVE_G2P[system]
                ipa, residual_set = native_g2p.to_ipa(t, script)
                residual = sorted(residual_set)
                conf = "high" if not residual else "medium"
                for c in residual:
                    residual_by_list[ident][c] += 1
                native_review.append((ident, r["lang_code"], r["gloss"], t, ipa,
                                      "".join(residual)))
            elif system == "native:Cyrillic" and r["lang_code"] in CYRILLIC_G2P \
                    and is_cyrillic(t):
                ipa, residual_set = cyrillic_g2p.to_ipa(t, r["lang_code"])
                residual = sorted(residual_set)
                conf = "high" if not residual else "medium"
                method = "cyrillic_g2p"
                for c in residual:
                    residual_by_list[ident][c] += 1
                cyrillic_review.append((ident, r["lang_code"], r["gloss"], t, ipa,
                                        "".join(residual)))
            elif (system.startswith("native:") and r["lang_code"] in ROMANIZE
                  and is_latin_line(t)):
                ipa, residual_set = ROMANIZE[r["lang_code"]](t)
                residual = sorted(residual_set)
                conf = "high" if not residual else "medium"
                method = "romanization"
                for c in residual:
                    residual_by_list[ident][c] += 1
                romanization_review.append((ident, r["lang_code"], r["gloss"], t, ipa,
                                            "".join(residual)))
            elif system == "native:Han" and r["lang_code"] == "cmn" and t in cmn_map:
                ipa, residual_set = pinyin_g2p.to_ipa(cmn_map[t])
                residual = sorted(residual_set)
                conf = "high" if not residual else "medium"
                method = "cmn"
                for c in residual:
                    residual_by_list[ident][c] += 1
                cmn_review.append((ident, r["lang_code"], r["gloss"],
                                   t + " " + cmn_map[t], ipa, "".join(residual)))
            elif system.startswith("native:"):
                method = "deferred_native"
            else:  # light_ipa, latin_diacritic, plain_ascii
                method = "deferred_latin"

            methods[method] += 1
            if conf:
                conf_count[(method, conf)] += 1
            rec = {"identifier": ident, "lang_code": r["lang_code"],
                   "gloss": r["gloss"], "canonical_gloss": r["canonical_gloss"],
                   "transcription_norm": t, "transcription_system": system,
                   "ipa": ipa, "ipa_method": method, "ipa_confidence": conf}
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")

    for path, rows in ((REVIEW, review), (SLAVIC_REVIEW, slavic_review),
                       (NATIVE_REVIEW, native_review), (CYR_REVIEW, cyrillic_review),
                       (ROM_REVIEW, romanization_review), (CMN_REVIEW, cmn_review)):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("identifier\tlang_code\tgloss\ttranscription_norm\tipa\tresidual\n")
            for row in sorted(rows):
                f.write("\t".join(row) + "\n")

    with open(SUMMARY, "w", encoding="utf-8", newline="\n") as f:
        f.write("# IPA conversion methods over all records.\n")
        f.write("method\tn_records\n")
        for m, n in methods.most_common():
            f.write(f"{m}\t{n}\n")
        f.write("\nmethod\tconfidence\tn_records\n")
        for (m, c), n in sorted(conf_count.items()):
            f.write(f"{m}\t{c}\t{n}\n")
        f.write("\n# Converted lists: residual (unconverted) symbols still present\n")
        f.write("identifier\tn_records_w_residual\tresidual_chars\n")
        for ident in sorted(residual_by_list):
            cc = residual_by_list[ident]
            chars = " ".join(f"{c}:{n}" for c, n in cc.most_common())
            f.write(f"{ident}\t{sum(cc.values())}\t{chars}\n")

    tier2 = (methods["greek_g2p"] + methods["kana_g2p"] + methods["cyrillic_g2p"]
             + methods["romanization"] + methods["cmn"])
    conv = (methods["native_ipa"] + methods["americanist"]
            + methods["slavic_g2p"] + tier2)
    print(f"records processed : {sum(methods.values())}  -> {OUT}")
    print("methods:")
    for m, n in methods.most_common():
        print(f"  {m:<18}{n:>7}")
    print(f"\nIPA populated now : {conv} records "
          f"({methods['americanist']} Americanist + {methods['slavic_g2p']} Slavic, Tier 1; "
          f"{methods['greek_g2p']} Greek + {methods['kana_g2p']} Kana + "
          f"{methods['cyrillic_g2p']} Cyrillic + {methods['romanization']} romanization + "
          f"{methods['cmn']} Mandarin, Tier 2)")
    print(f"review -> {REVIEW}")
    print(f"slavic -> {SLAVIC_REVIEW}")
    print(f"native -> {NATIVE_REVIEW}")
    print(f"cyril  -> {CYR_REVIEW}")
    print(f"roman  -> {ROM_REVIEW}")
    print(f"cmn    -> {CMN_REVIEW}")
    print(f"summary -> {SUMMARY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
