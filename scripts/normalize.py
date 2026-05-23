#!/usr/bin/env python3
"""Normalize the raw Rosetta Project Swadesh corpus into one structured dataset.

Reads data/raw/*.txt (verbatim Internet Archive files) and writes:
  - data/normalized/swadesh.jsonl   one JSON record per (list, gloss) entry
  - data/normalized/glossary.tsv    gloss inventory + cross-list frequency
  - metadata/normalize_report.tsv   per-file parse stats (lines/kept/dropped)

Idempotent: regenerates every output from scratch on each run.

Format handling (see TODO.md FINDINGS for how these were discovered):
  - 1227 standard files: UTF-8, "english_gloss: transcription", split on the
    FIRST colon only -- the transcription itself uses ':' as an IPA length mark
    (e.g. "all: ʔe:").
  - eng_swadesh-2: the canonical 207-item master list. TAB-delimited + numbered
    ("\\t<n>.\\t<word>"), NO transcription. Used here as the master gloss inventory.
  - hun_swadesh-2: "The 300 Languages Project". CP1250 (NOT UTF-8), dash-delimited
    "english - translation", with a 4-line prose header that we skip.

Transcription normalization is conservative and lossless-by-default:
  - transcription_raw keeps the decoded source text verbatim.
  - transcription_norm applies only safe, well-motivated fixes:
      * Unicode NFC
      * whitespace trim + internal-whitespace collapse
      * U+01DD (LATIN SMALL LETTER TURNED E, mis-used for schwa) -> U+0259 (ə)
  - Cyrillic 'й' (U+0439) is deliberately left ALONE. It is a confusable for /j/
    in the Latin-script lists, but a genuine letter in the Cyrillic-script lists
    (rus/bul/mdf), so a blanket replacement would silently corrupt those. Per-list
    script disambiguation is deferred (see TODO.md).
"""
import glob
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw")
OUT_DIR = os.path.join(ROOT, "data", "normalized")
MANIFEST = os.path.join(ROOT, "metadata", "manifest.json")
JSONL = os.path.join(OUT_DIR, "swadesh.jsonl")
GLOSSARY = os.path.join(OUT_DIR, "glossary.tsv")
COVERAGE = os.path.join(OUT_DIR, "canonical_coverage.tsv")
REPORT = os.path.join(ROOT, "metadata", "normalize_report.tsv")
ALIASES = os.path.join(ROOT, "metadata", "gloss_aliases.tsv")

MASTER = "rosettaproject_eng_swadesh-2"  # canonical 207-item gloss list
HUN300 = "rosettaproject_hun_swadesh-2"  # CP1250 dash-delimited 300-Languages list

# Confusables applied to transcription_norm. Latin-internal only; see module docstring.
CONFUSABLES = {"ǝ": "ə"}  # turned-e -> schwa
_CONFUSE_RE = re.compile("|".join(map(re.escape, CONFUSABLES)))
_WS_RE = re.compile(r"\s+")


def decode(path):
    """Decode a raw file, returning (text, encoding). UTF-8 with a CP1250 fallback."""
    raw = open(path, "rb").read()
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("cp1250"), "cp1250"  # only hun_swadesh-2 needs this


def norm_gloss(g):
    """Alignment key for a gloss: NFC, lowercased, whitespace-collapsed, trimmed.

    Parentheticals are preserved -- (incl.)/(excl.) and (singular)/(plural) are
    semantic disambiguators in the canonical list, and (n.)/(v.) distinguish real
    senses (e.g. the insect "fly (n.)" vs the verb "fly (v.)").
    """
    return _WS_RE.sub(" ", unicodedata.normalize("NFC", g).strip().lower())


def norm_transcription(t):
    t = unicodedata.normalize("NFC", t).strip()
    t = _CONFUSE_RE.sub(lambda m: CONFUSABLES[m.group(0)], t)
    return _WS_RE.sub(" ", t)


def parse_colon(text):
    """Standard list: 'gloss: transcription', split on the FIRST colon. Yields
    (gloss_raw, transcription_raw). A line with no colon is a gloss with no value."""
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if ":" in s:
            g, t = s.split(":", 1)
            yield g.strip(), t.strip()
        else:
            yield s, ""


def parse_master(text):
    """eng_swadesh-2: '\\t<n>.\\t<word>'. Yields (gloss_raw, '') in canonical order."""
    for ln in text.splitlines():
        if not ln.strip():
            continue
        parts = ln.split("\t")
        # ['', '1.', 'I'] -> word is the last non-empty field
        word = parts[-1].strip()
        if word:
            yield word, ""


def parse_hun300(text):
    """hun_swadesh-2: 'english - translation' after a prose header. Split on first ' - '."""
    for ln in text.splitlines():
        s = ln.strip()
        if " - " not in s:  # skips the 4-line header and blank lines
            continue
        g, t = s.split(" - ", 1)
        yield g.strip(), t.strip()


def load_aliases():
    """surface gloss (norm_gloss key) -> canonical gloss (norm_gloss key).

    Curated in metadata/gloss_aliases.tsv. Conservative: only unambiguous
    synonyms/typos/variants; genuine extra concepts and ambiguous glosses are
    intentionally absent (see that file's header)."""
    aliases = {}
    with open(ALIASES, encoding="utf-8") as f:
        for ln in f:
            ln = ln.rstrip("\n")
            if not ln.strip() or ln.lstrip().startswith("#"):
                continue
            parts = ln.split("\t")
            if len(parts) < 2 or parts[0] == "alias":  # skip header row
                continue
            alias, canon = norm_gloss(parts[0]), norm_gloss(parts[1])
            if alias and canon:
                aliases[alias] = canon
    return aliases


def load_titles():
    """identifier -> human-readable language name (from the manifest title)."""
    docs = json.load(open(MANIFEST, encoding="utf-8"))["response"]["docs"]
    titles = {}
    for d in docs:
        title = (d.get("title") or "").strip()
        name = re.sub(r"\s+Swadesh List$", "", title, flags=re.I) or None
        titles[d["identifier"]] = name
    return titles


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    titles = load_titles()
    files = sorted(glob.glob(os.path.join(RAW_DIR, "*.txt")))

    # First pass: the canonical 207 master inventory (preserves order + membership).
    master_text, _ = decode(os.path.join(RAW_DIR, MASTER + ".txt"))
    canonical = []
    seen = set()
    for g, _ in parse_master(master_text):
        k = norm_gloss(g)
        if k not in seen:
            seen.add(k)
            canonical.append(k)
    canonical_set = set(canonical)

    aliases = load_aliases()
    # Sanity: an alias target should itself be canonical (except deliberate
    # surface-only unifications onto a non-canonical concept, e.g. "claw").
    noncanon_targets = sorted({v for v in aliases.values() if v not in canonical_set})

    gloss_lists = {}  # surface gloss -> set of identifiers that contain it
    concept_lists = {}  # canonical_gloss (post-alias) -> set of identifiers
    report_rows = []
    n_records = 0
    n_aliased = 0

    with open(JSONL, "w", encoding="utf-8", newline="\n") as out:
        for path in files:
            ident = os.path.splitext(os.path.basename(path))[0]
            m = re.match(r"rosettaproject_(.+)_swadesh-(\d+)$", ident)
            lang_code, variant = (m.group(1), int(m.group(2))) if m else (ident, 0)
            text, enc = decode(path)

            if ident == MASTER:
                parser, kind = parse_master, "gloss-only"
            elif ident == HUN300:
                parser, kind = parse_hun300, "translation"
            else:
                parser, kind = parse_colon, "transcription"

            kept = dropped = 0
            seen_pairs = set()  # dedupe identical (gloss, transcription) within a file
            for gloss_raw, tr_raw in parser(text):
                gloss = norm_gloss(gloss_raw)
                if not gloss:
                    dropped += 1
                    continue
                tr_norm = norm_transcription(tr_raw)
                pair = (gloss, tr_norm)
                if pair in seen_pairs:
                    dropped += 1
                    continue
                seen_pairs.add(pair)
                canonical_gloss = aliases.get(gloss, gloss)
                if canonical_gloss != gloss:
                    n_aliased += 1
                rec = {
                    "identifier": ident,
                    "lang_code": lang_code,
                    "variant": variant,
                    "language": titles.get(ident),
                    "kind": kind,
                    "gloss": gloss,
                    "gloss_raw": gloss_raw,
                    "canonical_gloss": canonical_gloss,
                    "in_canonical": canonical_gloss in canonical_set,
                    "transcription_raw": tr_raw,
                    "transcription_norm": tr_norm,
                }
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                gloss_lists.setdefault(gloss, set()).add(ident)
                concept_lists.setdefault(canonical_gloss, set()).add(ident)
                kept += 1
                n_records += 1
            report_rows.append((ident, enc, kind, kept, dropped))

    rank = {k: i + 1 for i, k in enumerate(canonical)}

    # Glossary: every distinct SURFACE gloss, its list frequency, and what canonical
    # concept it folds onto (canonical_gloss == gloss when it is not an alias).
    with open(GLOSSARY, "w", encoding="utf-8", newline="\n") as g:
        g.write("gloss\tn_lists\tcanonical_gloss\tin_canonical\tcanonical_rank\n")
        for gloss in sorted(gloss_lists, key=lambda k: (-len(gloss_lists[k]), k)):
            canon = aliases.get(gloss, gloss)
            g.write(f"{gloss}\t{len(gloss_lists[gloss])}\t{canon}\t"
                    f"{int(canon in canonical_set)}\t{rank.get(canon, '')}\n")

    # Coverage: the 207 canonical concepts in rank order, with how many lists attest
    # each AFTER alias resolution -- the payoff of the alias map. Plus the largest
    # non-canonical concepts (extra glosses the corpus carries beyond the 207).
    with open(COVERAGE, "w", encoding="utf-8", newline="\n") as c:
        c.write("canonical_rank\tconcept\tn_lists\tin_canonical\n")
        for k in canonical:
            c.write(f"{rank[k]}\t{k}\t{len(concept_lists.get(k, ()))}\t1\n")
        extras = sorted(((k, v) for k, v in concept_lists.items()
                         if k not in canonical_set), key=lambda kv: -len(kv[1]))
        for k, ids in extras:
            c.write(f"\t{k}\t{len(ids)}\t0\n")

    with open(REPORT, "w", encoding="utf-8", newline="\n") as r:
        r.write("identifier\tencoding\tkind\tkept\tdropped\n")
        for row in report_rows:
            r.write("\t".join(map(str, row)) + "\n")

    n_lists = len(files)
    surface_cov = sum(1 for k in canonical if k in gloss_lists)
    concept_cov = sum(1 for k in canonical if concept_lists.get(k))
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"lists processed     : {n_lists}")
    print(f"records written     : {n_records}  -> {JSONL}")
    print(f"distinct surface gl.: {len(gloss_lists)}  -> {GLOSSARY}")
    print(f"alias rules loaded  : {len(aliases)}  ({n_aliased} records folded)")
    if noncanon_targets:
        print(f"  surface-only folds (target not canonical): {noncanon_targets}")
    print(f"canonical 207 items : {len(canonical)}")
    print(f"  attested by surface gloss : {surface_cov}/207")
    print(f"  attested after aliasing   : {concept_cov}/207  -> {COVERAGE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
