# TODO

## In progress / done
- [x] **Download the Swadesh lists** from the Rosetta collection on the Internet Archive.
      Source is NOT the blog page directly — the blog points to archive.org. See FINDINGS.
      Downloader: `scripts/download.py` (idempotent/resumable, 12-way concurrent).
      RESULT: **1229/1229 downloaded, 0 failures** (`data/raw/`, 7.8 MB). The 17 transient
      HTTP 500s on the first pass all succeeded on a second idempotent re-run.
- [x] **Investigate regularity of the corpus; how many separate categories are there?**
      ANSWERED. Format is HIGHLY regular (see FINDINGS - format regularity); gloss inventory
      + cross-list alignment in `data/normalized/glossary.tsv` (315 surface glosses; all 207
      canonical items appear; eye/fire/i/head/dog occur in ~1100/1229 lists). CATEGORIES
      formalized by `scripts/templates.py` -> `data/normalized/list_templates.tsv` +
      `metadata/template_summary.tsv`. Five categories by extension profile:
      core_swadesh 467, sahul_extended 449, extended_worldwide 189, lightly_extended 108,
      stub 16. See FINDINGS (template taxonomy).
- [x] **Store normalized versions of them all** (parse `gloss: transcription`, dedupe lines,
      normalize encoding quirks). DONE: `scripts/normalize.py` -> `data/normalized/swadesh.jsonl`
      (295,369 records; 72 MB, gitignored — regenerate with `python scripts/normalize.py`).
      Each record: {identifier, lang_code, variant, language, kind, gloss, gloss_raw,
      in_canonical, transcription_raw, transcription_norm}. Conservative norm (NFC, ws-collapse,
      U+01DD->U+0259); raw kept verbatim. Per-file stats in `metadata/normalize_report.tsv`.
- [ ] (STRATEGY) Structured representations (?) of IPA: e.g., "glottal fricative" instead of raw symbol.
- [ ] (STRATEGY) Somehow leverage known tendencies of IPA drift from known languages.

## Next concrete steps (for upcoming loop passes)
1. [x] **Gloss canonicalization / alignment cleanup.** DONE. Curated alias map in
   `metadata/gloss_aliases.tsv` (22 rules), applied by normalize.py as a new lossless
   `canonical_gloss` field (surface `gloss` kept verbatim). New report
   `data/normalized/canonical_coverage.tsv` = the 207 concepts by post-alias attestation.
   RESULT: 10,433 records folded; the big wins are pronoun/man concepts that were attested
   in only ~2 lists (just the English reference lists) because the corpus uses the
   Swadesh-100 surface forms: thou->you (singular) 2->1109, man->man (adult male) 2->1096,
   person->man (human being) 2->660, he/she->he 138->859, ye->you (plural) 2->16, large->big.
   Canonical items attested in >=500 lists: 134->138; median coverage 666->681.
   DELIBERATELY left unmapped (ambiguous, flagged in the alias file header): you, fly,
   grease, woods, breat, tsy, male/female. NEXT refinement: resolve those few by sampling
   the actual transcriptions / etymology, and consider male->man (adult male)/female->woman.
2. [x] **Template taxonomy (enumerate the categories).** DONE: `scripts/templates.py` ->
   `data/normalized/list_templates.tsv` + `metadata/template_summary.tsv`. See FINDINGS
   (template taxonomy). Possible refinement: sub-cluster within sahul_extended (Australian vs
   New Guinea), and detect a possible source/project signature per template.
3. **Confusable normalization, done safely (deferred from normalize.py).** Cyrillic 'й'
   (186 occ / 22 files) is a /j/ confusable in Latin-script lists BUT a real letter in the
   Cyrillic-script lists (rus/bul/mdf). Add per-list script detection, then map 'й'->'j' ONLY
   in predominantly-Latin lists. Survey other confusables (e.g. Greek vs Latin look-alikes).
4. Structured IPA features (TODO above): tokenize transcription_norm into IPA segments;
   attach phonetic features (place/manner/voicing) per segment.
5. (optional) The 8 non-Swadesh items + the 16 stub lists (<10 entries) are out of scope /
   unusable. Now flagged: category="stub" in list_templates.tsv marks the tiny lists.

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

## FINDINGS (gloss canonicalization + corpus is a SUPERSET of the 207)
- The corpus is a SUPERSET of the canonical 207, not just spelling drift. After folding the
  22 true aliases, ~90 distinct non-canonical concepts remain that are GENUINE extra glosses
  (left unmapped on purpose). They cluster into recognizable extended templates -> a partial
  answer to "how many categories": beyond core-207 lists there are regional/extended
  variants, notably an **Australianist template** (emu 412, crocodile 399, kangaroo 166,
  wallaby 313, cassowary 275, woomera 69, boomerang-style items) and broad **body-part**
  (shoulder 537, chin 443, navel 434, elbow 481, thigh 416, forehead 454, chest 434) and
  **kinship** (brother 584, sister 540, son 211, daughter 201, boy 436, girl 415) extensions,
  plus **time** (tomorrow 492, yesterday 473, morning 382) and rich **pronoun clusivity/dual**
  marking (we incl./excl., we two, you two, they two) common in Australian/Austronesian lists.
  NEXT: cluster lists by which extra-gloss template they follow to enumerate the categories.
- Aliasing is data-driven (`metadata/gloss_aliases.tsv`) + lossless (`canonical_gloss` field;
  surface `gloss` untouched), so judgement calls stay reviewable and reversible.

## FINDINGS (template taxonomy — scripts/templates.py)
Co-occurrence (Jaccard) shows the extensions are NOT many independent traditions but mostly
ONE shared extended fieldwork questionnaire (~200 items) used worldwide, plus a regional add-on
and one grammatical dimension. Blocks (non-canonical glosses that co-occur tightly), present in
a list when it has >= min_hits members:
  - sahul_fauna (>=2 of emu/kangaroo/wallaby/cassowary/crocodile/woomera) — Australia+New Guinea
    regional add-on; woomera lift 120x. 449 lists.
  - body_part (>=3 of arm/shoulder/elbow/chin/navel/thigh/calf/nape/...) — 605 lists.
  - kinship_age (brother/sister 0.87, boy/girl 0.79; +son/daughter) — 595 lists.
  - time_deixis (tomorrow/yesterday 0.85; +morning/today) — 499 lists.
  - weather (thunder/lightning 0.78) — 296 lists.
  - dual_clusivity (you two/they two 0.90; we incl./excl., we two) — 424 lists, ORTHOGONAL:
    spread across ALL categories & families (Khoisan, Andamanese, NE Caucasian, Ainu, Papuan)
    => a real grammatical feature, reported as its own flag, not a category.
PRIMARY CATEGORIES (one per list, `data/normalized/list_templates.tsv`):
  core_swadesh 467 (med 101 entries, ~100 canonical, ~2 extras — the classic lists),
  sahul_extended 449 (med 337 entries; PNG/Australian), extended_worldwide 189 (the same big
  questionnaire minus Sahul fauna — e.g. the Andamanese Aka-* family lands here 6/7),
  lightly_extended 108, stub 16 (med 2 entries, unusable).
Validation: Aka-* (Andamanese) -> extended_worldwide as predicted; core_swadesh lists really do
have ~0 block members. Slide deck of this analysis: `slides/swadesh-clusters.html`.
