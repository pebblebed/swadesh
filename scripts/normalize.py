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
      * wrong-SCRIPT confusables, PER-LINE gated: a non-Latin codepoint typed
        where a Latin/IPA symbol was meant is fixed ONLY in transcriptions that
        are themselves predominantly Latin-script. Two kinds: pure homoglyphs
        (Cyrillic й->j е->e ј->j І->i ӓ->ä ӧ->ö ӡ->ʒ; Greek look-alikes) and
        phonetic-value confusables (Greek φ->ɸ ε->ɛ γ->ɣ δ->ð η->ŋ λ->ɬ; Cyrillic
        ш->ʃ ф->f). Per-language overrides (LANG_CONFUSABLES) resolve the
        Caucasian ӡ->d͡z (abk/abq/ady/kbd/bbl). Genuine native transcriptions --
        the Cyrillic lines in bul/rus/mdf, the all-Greek ell list, the Arabic/Thai
        native lines -- are never touched; Greek β/θ/χ are kept (valid IPA). See
        SCRIPT_CONFUSABLES below + metadata/confusables_report.tsv (applied +
        still-flagged candidates, notably Cyrillic э).
"""
import collections
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
CONFUSE_REPORT = os.path.join(ROOT, "metadata", "confusables_report.tsv")

MASTER = "rosettaproject_eng_swadesh-2"  # canonical 207-item gloss list
HUN300 = "rosettaproject_hun_swadesh-2"  # CP1250 dash-delimited 300-Languages list

# --- Confusable normalization (transcription_norm only; raw kept verbatim) ---
# (1) Latin-internal, ALWAYS safe: turned-e mis-used for schwa.
CONFUSABLES = {"ǝ": "ə"}  # U+01DD -> U+0259
_CONFUSE_RE = re.compile("|".join(map(re.escape, CONFUSABLES)))

# (2) Wrong-SCRIPT confusables: a non-Latin codepoint typed where a Latin/IPA
# symbol was meant. Applied ONLY to a transcription that is itself predominantly
# Latin-script (the _latin_dominant gate below), so genuine Cyrillic/Greek/Arabic
# transcriptions -- the Cyrillic lines interleaved in bul/rus/mdf, the all-Greek
# ell list, the Arabic/Thai native lines -- are NEVER touched. Each value was set
# from a corpus survey of actual usage (see metadata/confusables_report.tsv and
# TODO 'confusable survey').
#   Two kinds: (a) pure homoglyphs (the Cyrillic/Greek glyph is identical to a
#   Latin/IPA one) and (b) phonetic-value confusables (a wrong-script letter used
#   for its sound -- NOT its look-alike: Cyrillic с is /s/, not Latin c).
#   Deliberately NOT mapped:
#     - β θ χ : these Greek codepoints ARE valid IPA (voiced bilabial / voiceless
#               dental / voiceless uvular fricatives); Unicode has no Latin form.
#     - э     : ambiguous between schwa /ə/ and /ɛ/ across the ~20 Austronesian
#               lists that use it (they already use ə separately) -- left flagged.
SCRIPT_CONFUSABLES = {
    # -- Greek-for-IPA (the symbol exists in IPA as a Latin-block codepoint) --
    "φ": "ɸ",   # U+03C6 GREEK PHI          -> ɸ  U+0278 (bilabial fricative)
    "ε": "ɛ",   # U+03B5 GREEK EPSILON      -> ɛ  U+025B (open-mid front vowel)
    "γ": "ɣ",   # U+03B3 GREEK GAMMA        -> ɣ  U+0263 (velar fricative)
    "δ": "ð",   # U+03B4 GREEK DELTA        -> ð  U+00F0 (dental fricative)
    "ϑ": "θ",   # U+03D1 GREEK THETA SYMBOL -> θ  U+03B8 (the standard IPA theta)
    "ί": "i",   # U+03AF GREEK IOTA+TONOS   -> i  (stray accented vowel)
    "έ": "ɛ",   # U+03AD GREEK EPSILON+TONOS-> ɛ
    "η": "ŋ",   # U+03B7 GREEK ETA used for the velar nasal (biηtaŋ = bintaŋ)
    "λ": "ɬ",   # U+03BB GREEK LAMBDA = Caucasian voiceless lateral fricative ɬ
                #         (the lateral AFFRICATE is written ƛ U+019B, kept as-is)
    # -- pure homoglyphs (Cyrillic/Greek glyph identical to a Latin/IPA one) --
    "й": "j",   # U+0439 CYRILLIC SHORT I   -> j   (palatal approximant)
    "е": "e",   # U+0435 CYRILLIC IE        -> e
    "ј": "j",   # U+0458 CYRILLIC JE        -> j
    "І": "i",   # U+0406 CYRILLIC BYELORUSSIAN-UKRAINIAN I -> i
    "є": "ɛ",   # U+0454 CYRILLIC UKRAINIAN IE  ~ ɛ
    "ӓ": "ä",   # U+04D3 CYRILLIC A+DIAERESIS -> ä  (glyph-normalize; phon. ~ æ)
    "ӧ": "ö",   # U+04E7 CYRILLIC O+DIAERESIS -> ö  (glyph-normalize; phon. ~ ø)
    "ӯ": "ū",   # U+04EF CYRILLIC U+MACRON    -> ū
    "ӡ": "ʒ",   # U+04E1 CYRILLIC ABKHASIAN DZE ~ IPA ezh ʒ (Caucasus -> d͡z, below)
    # -- phonetic-value confusables (Cyrillic letter used for its sound) --
    "ш": "ʃ",   # U+0448 CYRILLIC SHA -> ʃ
    "Ш": "ʃ",   # U+0428 CYRILLIC capital SHA -> ʃ
    "ф": "f",   # U+0444 CYRILLIC EF  -> f
}
# Per-language overrides, applied (within the same Latin gate) before the table
# above. The Abkhasian Dze ӡ is the IPA ezh ʒ by default, but in these
# NW-Caucasian / Nakh lists it is the voiced alveolar affricate /d͡z/ -- e.g.
# Abkhaz 'water' аӡы = [aˈd͡zə], Kabardian 'tooth' ӡa = [d͡za].
LANG_CONFUSABLES = {lc: {"ӡ": "d͡z"} for lc in ("abk", "abq", "ady", "kbd", "bbl")}
_LEGIT_IPA_GREEK = set("βθχ")  # valid-IPA Greek codepoints: never flag as foreign

_NONLATIN_RANGES = [
    (0x0400, 0x04FF, "Cyrillic"), (0x0370, 0x03FF, "Greek"),
    (0x0590, 0x05FF, "Hebrew"), (0x0600, 0x06FF, "Arabic"),
    (0x0900, 0x097F, "Devanagari"), (0x0E00, 0x0E7F, "Thai"),
    (0x3040, 0x30FF, "Kana"), (0x4E00, 0x9FFF, "Han"), (0x3400, 0x4DBF, "Han"),
    (0xAC00, 0xD7A3, "Hangul"),
]
_WS_RE = re.compile(r"\s+")


def script_of(c):
    cp = ord(c)
    for lo, hi, name in _NONLATIN_RANGES:
        if lo <= cp <= hi:
            return name
    return "Latin"  # Latin blocks + IPA extensions + modifier/combining marks


def _latin_dominant(t):
    """True if Latin-family letters are at least as many as the largest single
    non-Latin script in the string (and there is at least one Latin letter).
    This per-line test is what makes a stray Cyrillic/Greek letter a confusable
    rather than genuine native content."""
    counts = collections.Counter(script_of(c) for c in t if c.isalpha())
    latin = counts.get("Latin", 0)
    if not latin:
        return False
    other_max = max((v for k, v in counts.items() if k != "Latin"), default=0)
    return latin >= other_max


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


def norm_transcription(t, lang=""):
    """Normalize a transcription for transcription_norm. Returns
    (norm, applied, flagged): `applied` lists (src, dst) confusable pairs that
    were replaced; `flagged` lists foreign-script letters left UNMAPPED in a
    Latin-dominant line (survey candidates -- recorded for review, not changed).
    Wrong-script confusables fire only when the line is Latin-dominant; `lang`
    selects any per-language override (LANG_CONFUSABLES)."""
    t = unicodedata.normalize("NFC", t).strip()
    t = _CONFUSE_RE.sub(lambda m: CONFUSABLES[m.group(0)], t)
    applied, flagged = [], []
    if _latin_dominant(t):
        overrides = LANG_CONFUSABLES.get(lang, {})
        out = []
        for c in t:
            repl = overrides.get(c) or SCRIPT_CONFUSABLES.get(c)
            if repl is not None:
                applied.append((c, repl))
                out.append(repl)
            else:
                if c.isalpha() and c not in _LEGIT_IPA_GREEK and script_of(c) != "Latin":
                    flagged.append(c)
                out.append(c)
        t = "".join(out)
    return _WS_RE.sub(" ", t), applied, flagged


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
    applied_stats = collections.defaultdict(lambda: [0, set()])   # char -> [occ, lists]
    flagged_stats = collections.defaultdict(lambda: [0, set()])   # char -> [occ, lists]

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
                tr_norm, applied_cs, flagged_cs = norm_transcription(tr_raw, lang_code)
                pair = (gloss, tr_norm)
                if pair in seen_pairs:
                    dropped += 1
                    continue
                seen_pairs.add(pair)
                for sd in applied_cs:               # sd = (src, dst)
                    applied_stats[sd][0] += 1
                    applied_stats[sd][1].add(ident)
                for c in flagged_cs:
                    flagged_stats[c][0] += 1
                    flagged_stats[c][1].add(ident)
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

    # Confusables report: what was mapped (applied) + foreign letters left in
    # Latin-dominant lines that we did NOT map (flagged = future-work candidates).
    def _ex(lists):
        return " ".join(sorted(x.replace("rosettaproject_", "") for x in lists)[:6])
    with open(CONFUSE_REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Wrong-script confusables in transcription_norm (per-line Latin-gated).\n")
        f.write("# transcription_raw keeps the verbatim source, so this is reversible.\n")
        f.write("section\tchar\tmaps_to\tscript\toccurrences\tn_lists\texample_lists\n")
        for (c, repl) in sorted(applied_stats, key=lambda k: -applied_stats[k][0]):
            occ, lists = applied_stats[(c, repl)]
            f.write(f"applied\t{c}\t{repl}\t{script_of(c)}\t"
                    f"{occ}\t{len(lists)}\t{_ex(lists)}\n")
        for c in sorted(flagged_stats, key=lambda c: -flagged_stats[c][0]):
            occ, lists = flagged_stats[c]
            f.write(f"flagged\t{c}\t\t{script_of(c)}\t{occ}\t{len(lists)}\t{_ex(lists)}\n")

    n_lists = len(files)
    surface_cov = sum(1 for k in canonical if k in gloss_lists)
    concept_cov = sum(1 for k in canonical if concept_lists.get(k))
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"lists processed     : {n_lists}")
    print(f"records written     : {n_records}  -> {JSONL}")
    print(f"distinct surface gl.: {len(gloss_lists)}  -> {GLOSSARY}")
    print(f"alias rules loaded  : {len(aliases)}  ({n_aliased} records folded)")
    n_applied = sum(v[0] for v in applied_stats.values())
    applied_desc = ", ".join(f"{c}->{repl}:{applied_stats[(c, repl)][0]}"
                             for (c, repl) in sorted(applied_stats, key=lambda k: -applied_stats[k][0]))
    print(f"confusables applied : {n_applied} chars in Latin-dominant lines "
          f"({applied_desc})")
    print(f"  flagged (unmapped): {sum(v[0] for v in flagged_stats.values())} chars "
          f"-> {CONFUSE_REPORT}")
    if noncanon_targets:
        print(f"  surface-only folds (target not canonical): {noncanon_targets}")
    print(f"canonical 207 items : {len(canonical)}")
    print(f"  attested by surface gloss : {surface_cov}/207")
    print(f"  attested after aliasing   : {concept_cov}/207  -> {COVERAGE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
