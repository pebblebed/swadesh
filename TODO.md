# TODO

## In progress / done
- [x] **Download the Swadesh lists** from the Rosetta collection on the Internet Archive.
      Source is NOT the blog page directly — the blog points to archive.org. See FINDINGS.
      Downloader: `scripts/download.py` (idempotent/resumable, 12-way concurrent).
      RESULT: **1229/1229 downloaded, 0 failures** (`data/raw/`, 7.8 MB). The 17 transient
      HTTP 500s on the first pass all succeeded on a second idempotent re-run.
- [x] **Investigate regularity of the corpus; how many separate categories are there?**
      Strong result: the corpus is HIGHLY regular (see FINDINGS - format regularity).
      Gloss inventory + cross-list alignment now built (`data/normalized/glossary.tsv`):
      315 distinct glosses; all 207 canonical items appear; the most universal glosses
      (eye/fire/i/head/dog) occur in ~1100/1229 lists. See FINDINGS (normalize results).
- [x] **Store normalized versions of them all** (parse `gloss: transcription`, dedupe lines,
      normalize encoding quirks). DONE: `scripts/normalize.py` -> `data/normalized/swadesh.jsonl`
      (295,369 records; 72 MB, gitignored — regenerate with `python scripts/normalize.py`).
      Each record: {identifier, lang_code, variant, language, kind, gloss, gloss_raw,
      in_canonical, transcription_raw, transcription_norm}. Conservative norm (NFC, ws-collapse,
      U+01DD->U+0259); raw kept verbatim. Per-file stats in `metadata/normalize_report.tsv`.
- [ ] (STRATEGY) Structured representations (?) of IPA: e.g., "glottal fricative" instead of raw symbol.
- [ ] (STRATEGY) Somehow leverage known tendencies of IPA drift from known languages.

## Next concrete steps (for upcoming loop passes)
1. **Gloss canonicalization / alignment cleanup.** 315 distinct glosses vs 207 canonical.
   The extras are near-synonyms & noise: "thou" (1107 lists) and "man" (1094) are widespread
   but DON'T match canonical ("you (singular)", "man (adult male)") because of parenthetical
   /spelling differences; plus typos ("tonge", "snooth", "tsy"). Build a gloss-alias map
   (thou->you (singular), etc.) + fix obvious typos, so the ~1100-list-wide glosses fold onto
   canonical ranks. Lets us assemble a clean (gloss x language) cognate matrix.
2. **Confusable normalization, done safely (deferred from normalize.py).** Cyrillic 'й'
   (186 occ / 22 files) is a /j/ confusable in Latin-script lists BUT a real letter in the
   Cyrillic-script lists (rus/bul/mdf). Add per-list script detection, then map 'й'->'j' ONLY
   in predominantly-Latin lists. Survey other confusables (e.g. Greek vs Latin look-alikes).
3. Structured IPA features (TODO above): tokenize transcription_norm into IPA segments;
   attach phonetic features (place/manner/voicing) per segment.
4. (optional) The 8 non-Swadesh items + the 5 stub lists (<10 entries, e.g. akq="thou: ni")
   are out of scope / unusable — leave excluded, but a flag in the dataset could note tiny lists.

## FINDINGS (data source & format)
- Blog post: rosettaproject.org/blog/02010/sep/20/Rosetta_Project_Swadesh_List_Data/
  -> data actually lives at the Internet Archive in collection `rosettaproject`.
- Search API: https://archive.org/advancedsearch.php?q=swadesh+collection%3Arosettaproject
  Returns numFound = **1237** items. Saved to `metadata/manifest.json` (identifier, language, title).
- Of the 1237: **1229 are true Swadesh lists** (`rosettaproject_<code>_swadesh-<N>`); **8 are
  other linguistic data** (suffixes `_vocab-N`, `_morsyn-1`, `_phon-1`, `_contents-1`), e.g.
  `rosettaproject_arg_vocab-1`, `rosettaproject_ynn_morsyn-1`. These matched the search but are
  out of scope for the Swadesh corpus.
- List variants: 1223 are `swadesh-1`, 5 are `swadesh-2`, 1 is `swadesh-3` (multiple
  varieties/sources per language). Language code `hun` therefore appears twice -> we name local
  files by full **identifier** (`data/raw/<identifier>.txt`) to avoid collisions.
- Item file layout (example `rosettaproject_puo_swadesh-1`): `<code>.txt` (the data),
  plus `<code>.txt_meta.txt`, `*_files.xml`, `*_meta.xml`, `*_archive.torrent`.
- Download URL: https://archive.org/download/<identifier>/<code>.txt (302-redirects to a
  regional iaXXXXXX.us.archive.org mirror; urllib/curl follow it automatically).

## FINDINGS (file format — `<code>.txt`)
- UTF-8 text, one entry per line: `english_gloss: transcription`.
- Separator is the FIRST colon. NOTE: the transcription ALSO contains colons as IPA length
  marks (e.g. `all: ʔe:`), so split on the first `:` only.
- Glosses may carry POS parentheticals, e.g. `fly (v.)`.
- Quirk 1: duplicate lines occur (e.g. `man: kho:n sa:j` twice in puo) -> dedupe on normalize.
- Quirk 2: **stray look-alike characters mixed into IPA.** Two cases, corrected after a
  full-corpus codepoint scan (earlier guesses in this file were off):
  * The schwa substitute is **U+01DD LATIN SMALL LETTER TURNED E** (`ǝ`), NOT U+04DD. It's a
    Latin letter mis-used for schwa `ə` (U+0259). 588 records across the corpus. SAFE to map
    U+01DD->U+0259 -> **done in normalize.py** (transcription_norm only; raw kept verbatim).
  * `й` (U+0439, Cyrillic short-i) — 186 occ in 22 files. In Latin-script lists (puo etc.) it's
    a /j/ confusable, BUT in the genuinely Cyrillic-script lists (**rus/bul/mdf**) it is a real
    letter. A blanket й->j would CORRUPT those. So normalize.py leaves й ALONE; the safe fix
    needs per-list script detection (see Next steps #2).

## FINDINGS (format regularity — scan of all 1229 files)
The corpus is remarkably uniform. By fraction of non-blank lines containing a `:`:
- **1227 / 1229** files are >=95% colon lines = standard `gloss: transcription` (UTF-8). One category.
- **2 outliers** (both alternate-series, both 0 colons):
  - `eng_swadesh-2.txt` — the canonical **207-item** extended Swadesh list, TAB-delimited and
    line-numbered: `\t<n>.\t<english_word>`. NO transcription; this IS the reference gloss list /
    canonical ordering. Use it as the master gloss inventory.
  - `hun_swadesh-2.txt` — "The 300 Languages Project" (by Timea Rajtik). Format `english - translation`
    (DASH-delimited) with a 4-line header. **NOT UTF-8** (shows U+FFFD; Hungarian -> try CP1250/Latin-2).
=> normalize.py needs: a standard colon parser (1227 files), plus 2 special-case parsers, plus
   per-file encoding detection (don't assume UTF-8 everywhere).
CONFIRMED during normalize — the other variants are all standard colon format, but note their
"transcription" is not always IPA (recorded as `kind` in the dataset):
- `cmn_swadesh-2`: Chinese orthography (Hanzi), not IPA.   - `hin_swadesh-2`/`tgl_swadesh-2`: romanizations, with per-gloss synonyms on separate lines.
- `fra_swadesh-3`: French words with synonyms (e.g. `all: tous` / `all: tout`).

## FINDINGS (normalize.py results — full corpus pass)
- 1229 lists -> **295,369 records**, **315 distinct glosses** (data/normalized/swadesh.jsonl).
- Only **1** non-blank line in the entire colon corpus lacked a colon (tay "strike", no value)
  -> the `gloss: transcription` model is essentially exceptionless.
- **All 207 canonical glosses appear** in >=1 list. Most universal: eye(1152), fire(1149),
  i(1136), head(1135), dog(1128) — i.e. ~93% of lists. Strong cross-list alignment.
- 66,104 lines dropped as exact (gloss, norm-transcription) duplicates within their file.
- List-size distribution (entries kept per list): 16 stubs(<10), 84 small(10-49),
  216 partial(50-99), 333 standard(100-199), 580 large(200+). **913 lists have >=100 entries.**
- Encoding: 1228 files UTF-8, exactly 1 CP1250 (`hun_swadesh-2`, Hungarian é/ő/ű confirmed).
