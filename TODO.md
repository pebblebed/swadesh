# TODO

## In progress / done
- [x] **Download the Swadesh lists** from the Rosetta collection on the Internet Archive.
      Source is NOT the blog page directly — the blog points to archive.org. See FINDINGS.
      Downloader: `scripts/download.py` (idempotent/resumable, 12-way concurrent).
      RESULT: **1229/1229 downloaded, 0 failures** (`data/raw/`, 7.8 MB). The 17 transient
      HTTP 500s on the first pass all succeeded on a second idempotent re-run.
- [~] **Investigate regularity of the corpus; how many separate categories are there?**
      Strong result: the corpus is HIGHLY regular (see FINDINGS - format regularity).
      Still TODO: build the gloss inventory + measure cross-list gloss alignment.
- [ ] **Store normalized versions of them all** (parse `gloss: transcription`, dedupe lines,
      normalize encoding quirks — see FINDINGS).
- [ ] Structured representations (?) of IPA: e.g., "glottal fricative" instead of raw symbol.
- [ ] Strategy to leverage known tendencies of IPA drift from known languages.

## Next concrete steps (for upcoming loop passes)
1. Confirm download completed; inspect `download_failures.tsv`; re-run downloader to retry.
2. Decide handling of the 8 non-Swadesh items (vocab/morsyn/phon/contents) — exclude or
   archive separately. Currently EXCLUDED by `scripts/download.py` (filters `_swadesh-`).
3. Write `scripts/normalize.py`: parse each raw file into structured records, handle the
   encoding quirks below, dedupe repeated lines, emit a single normalized dataset
   (e.g. JSONL: {identifier, lang_code, gloss, transcription_raw, transcription_norm}).
4. Build a glossary: the set of distinct English glosses across all lists, to measure how
   "regular"/aligned the lists are (do they all use the same ~100/207 Swadesh items?).

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
- Quirk 2: **stray Cyrillic characters mixed into IPA** — `й` (U+0439) and `ǝ` vs `ə`. In puo,
  `ʔaй`, `йuk`, `ʔkiй` almost certainly mean a /j/ glide; `ǝ` (U+04DD) is being used for schwa
  `ə` (U+0259). Likely OCR/transcription artifacts -> build a confusable-normalization map.

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
NOTE: still need to confirm the format of the other multi-list variants (the 4 remaining swadesh-2
and the 1 swadesh-3) — they passed the colon test but eyeball them during normalize.
