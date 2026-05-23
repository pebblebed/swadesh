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
- [x] (STRATEGY) Structured representations of IPA: e.g., "glottal fricative" instead of raw symbol.
      DONE: `scripts/ipa_features.py` tokenizes the IPA layer into phonetic SEGMENTS and attaches
      articulatory features (consonant: voice/place/manner; vowel: height/backness/rounding; plus
      length, nasalized, syllabic, tone, secondary articulations). h -> "voiceless glottal
      fricative". 99.72% segment coverage over 149,952 records / 772,660 segments; 823 distinct
      known segments. Outputs: `data/normalized/ipa_features.jsonl` (per-record segments,
      gitignored/regen), `metadata/ipa_segment_inventory.tsv` + `ipa_features_summary.tsv`
      (TRACKED). Tokenizer: NFC -> PRESUB (caron/digraph consonants č->t͡ʃ etc.) -> NFD (so
      precomposed accented vowels split to base+diacritic) -> greedy segment (tie-bar affricates,
      trailing combining marks + spacing modifiers; ⁿ prenasalization attaches forward;
      dot-below=retroflex; ASCII ':' = length; non-phonetic punctuation skipped). Embedded
      self-test: 23 gold forms. Coverage 99.88% after the ß->β fix. REMAINING unknowns (0.12%):
      archiphoneme capitals (N/V/T cover symbols) + the deliberately-flagged Cyrillic э + mojibake.
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
3. [x] **IPA strategy Tier 0: classify transcription systems.** DONE: `scripts/classify_transcription.py`
   -> `data/normalized/transcription_systems.tsv` (per list, joins to list_templates.tsv on
   identifier) + `metadata/transcription_summary.tsv`. See "IPA CONVERSION STRATEGY" below.
4. [x] **Confusable normalization, done safely.** DONE in `normalize.py` via a PER-LINE
   (not per-list) Latin-dominance gate -- crucial because bul is Latin-DOMINANT overall (its
   romanized synonym lines outnumber its Cyrillic ones) yet its Cyrillic lines are genuine; a
   per-list gate would have corrupted them. A wrong-script char is mapped ONLY when its own
   transcription is predominantly Latin. Map (`SCRIPT_CONFUSABLES`): Cyrillic й->j (94 occ/19
   lists) + Greek-for-IPA φ->ɸ (1433/134!), ε->ɛ (298/11), γ->ɣ (15/4), δ->ð (10/4), ϑ->θ (4/1)
   Greek β/θ/χ DELIBERATELY kept (valid IPA codepoints). Genuine native lines verified untouched
   (bul 'майка', mdf 'шулей', ell 'μεγάλο' all preserved; raw kept verbatim so reversible).
   PASS 2 (homoglyphs + per-Caucasian resolution) added: pure homoglyphs е->e ј->j І->i ӓ->ä
   ӧ->ö ӯ->ū ί->i έ->ɛ є->ɛ; phonetic-value confusables η->ŋ (biηtaŋ=bintaŋ) ш->ʃ ф->f; the
   Caucasian lateral λ->ɬ (66/12 lists; the lateral AFFRICATE ƛ U+019B is left as-is); and
   ӡ resolved PER-LANGUAGE via `LANG_CONFUSABLES`: ӡ->d͡z in NW-Caucasian/Nakh (abk/abq/ady/
   kbd/bbl: Abkhaz 'water' аӡы=[aˈd͡zə]) but ӡ->ʒ elsewhere (the ezh homoglyph, ~16 Austroasiatic
   lists). PASS 3 added the Latin-block confusable ß->β (2238 occ across 215 phonetic lists --
   Papuan/African, often paired with ɸ; Hebrew/Syriac spirantized bet ~[v]/[β]) with per-language
   override deu->s (German 'groß'->gros). Now 4439 chars fixed; only 37 still FLAGGED -- Cyrillic
   э (36/19, genuinely ambiguous ə vs ɛ across Austronesian lists that ALSO use ə) + one stray
   Greek υ. Front vowels ӓ/ӧ kept
   as Latin ä/ö at this layer (phon. ~æ/ø) for a later IPA pass. SIDE EFFECT: cleaner IPA chars
   reclassified 12 lists -> ipa_dense (605->617); to_ipa now passes ~2,514 more recs (149,519
   total) through native_ipa. Full audit: `metadata/confusables_report.tsv`.
   NEXT: decide э per-list (sample whether it contrasts with ə); the ӓ/ӧ->æ/ø phonetic refinement
   belongs in the Caucasus IPA tier, not normalize.
5. [x] Structured IPA features. DONE (see STRATEGY item above): `scripts/ipa_features.py`,
   99.88% coverage. NEXT refinements: optionally capture tone numbers/downstep; map the few
   archiphoneme capitals if a per-list convention is found.
6. (optional) The 8 non-Swadesh items + the 16 stub lists (<10 entries) are out of scope /
   unusable. Now flagged: category="stub" in list_templates.tsv marks the tiny lists.

## IPA CONVERSION STRATEGY (tiered)  [Tier 0 DONE]
Problem: only ~half the corpus is usable IPA. Tier-0 audit (scripts/classify_transcription.py,
data/normalized/transcription_systems.tsv) over 1229 lists:
  ipa_dense 605 | light_ipa 321 | latin_diacritic 186 | plain_ascii 93 | americanist 12 |
  native scripts 11 (Arabic 3, Cyrillic 3, Greek/Han/Hebrew/Kana/Thai 1 each) | gloss_only 1.
  => 605 IPA-ready now; 623 need conversion. Each list has scores (ipa_density, ipa_char_ratio,
  nonascii_ratio, americanist_ratio) so thresholds stay re-judgeable.
PROGRESS (lists with IPA populated, by `python scripts/to_ipa.py`): 636 / 1229 lists ->
  617 ipa_dense (native_ipa) + 10 Americanist + 2 Czech/Slovak + 1 Greek + 1 Kana + 2 Cyrillic
  (rus/bul) + 2 romanization (arb/tha) + 1 Mandarin (cmn). By RECORDS: 150,362 / 295,369 have a
  non-empty `ipa`. Remaining native-script (Tier 2): ydd (do next), mdf (needs verification),
  pes/pbt abjads (defer). Plus ~555 Latin/light_ipa lists (Tier 3). STRUCTURED IPA FEATURES built
  on this layer (scripts/ipa_features.py, 99.88% segment coverage) -- growing IPA grows features.
Bonus: transcription system CORRELATES with template category. sahul_extended is mostly
  ipa_dense/light_ipa (real phonetic fieldwork); core_swadesh holds ALL 11 native-script lists
  and most orthographic ones (major languages in their own spelling).
PLAN (easiest -> hardest):
  - [x] Tier 1 Americanist->IPA. DONE: `scripts/to_ipa.py` builds the IPA layer
    `data/normalized/ipa.jsonl` (gitignored, regenerable) with per-record ipa / ipa_method /
    ipa_confidence. Methods: native_ipa (605 ipa_dense lists pass through, 143,423 recs),
    americanist (10 lists, 2,936 recs via `metadata/americanist_ipa_map.tsv`), slavic_g2p
    (Czech+Slovak, 361 recs), deferred_* (native 2,358, latin 146,078). Conservative map =
    caron core only (č->t͡ʃ ǯ/ǰ->d͡ʒ š->ʃ ž->ʒ ñ->ɲ); already-IPA symbols left as-is;
    tradition-specific symbols (j/y, dot-below emphatics, accents) left as flagged RESIDUALS.
    Result: 2,597 high-confidence + 339 medium. Czech+Slovak SPLIT OUT (carons are native
    orthography, handled by the Slavic G2P below). Human-review file:
    `data/normalized/ipa_americanist_review.tsv`; tallies `metadata/ipa_conversion_summary.tsv`.
    Cheyenne worst (62/188) due to '\' corruption + ê/ô/â orthography -> revisit under
    Tier 3 / data-cleanup.
  - [x] Tier 1 Slavic (Czech+Slovak) G2P. DONE: `scripts/slavic_g2p.py` (rule-based,
    NOT a flat char map) called from `to_ipa.py` as method `slavic_g2p`. Converts all 361
    ces/slk records, ALL high-confidence with ZERO residuals. Implements: digraphs (ch->x,
    SK dz/dž->affricates); palatalization (ď/ť/ň + SK ľ -> ɟ/c/ɲ/ʎ, and plain d/t/n + SK l
    before soft vowels -- CZ i/í/ě, SK i/í & the i-diphthongs); CZ ě glides (bě/pě/vě/fě->Cjɛ,
    mě->mɲɛ); vowel length á/é/í/ó/ú/ů/ý->Vː; SK diphthongs ia/ie/iu/ô + ä->æ; CZ ou/au/eu;
    syllabic r/l (krk->kr̩k, slnko->sl̩ŋkɔ); n->ŋ before velars; REGRESSIVE voicing assimilation
    + final devoicing (kde->ɡdɛ, vták->ftaːk, zub->zup, dážď->daːʃc); CZ ř progressive
    devoicing after voiceless (tři->tr̝̥ɪ); homorganic stop+affricate coalescence (srdce->sr̩t͡sɛ).
    Handles synonym lists (split on ,/;), multi-word forms (báť sa->baːc sa), and strips
    (m.)-type annotations. Embedded self-test: 59 hand-derived gold forms, run via
    `python scripts/slavic_g2p.py`. Review file: `data/normalized/ipa_slavic_review.tsv`.
    KNOWN LIMITATION (documented in module): SK d/t/n/l before plain 'e' NOT palatalized
    (lexical in Slovak: ten=[tɛn] vs deň=[ɟɛɲ]); we default to the majority hard reading.
    Other Slavic lists are NOT this tier: pol=latin_diacritic (Tier 3), rus/bul=Cyrillic (Tier 2).
  - Tier 1b (orig plan, superseded): y->j was DROPPED as unsafe -- several lists contrast
    j vs ǯ, so y/j values are list-specific. Resolve per-list if needed.
  - [x] Tier 2 Greek + Japanese-Kana G2P. DONE: `scripts/native_g2p.py` (rule-based),
    called from `to_ipa.py` as methods `greek_g2p` (207 ell recs) and `kana_g2p` (78 jpn recs).
    ALL 285 high-confidence, ZERO residuals (both lists are pristine: pure native script, no
    romanized synonyms / multi-word / punctuation). Greek (Modern std): vowel digraphs
    (αι=e ει/οι/υι=i ου=u); αυ/ευ -> a/e + v(before voiced)/f(voiceless/final) (αυγό=avˈɣo,
    αυτός=afˈtos); velar palatalization before front vowels κ->c γ->ʝ χ->ç (και=ce, νύχι=ˈniçi
    vs νύχτα=ˈnixta); prenasalized voiced-stop digraphs μπ/ντ/γκ -> b/d/ɡ initial, mb/nd/ŋɡ
    medial (πέντε=ˈpende), γγ=ŋɡ, τσ=t͡s τζ=d͡z ξ=ks ψ=ps, double-C simplification; σ->z before
    voiced C; SYNIZESIS (unstressed i + vowel glides: κοιλιά=ciˈʎa, ήλιος=ˈiʎos, χιόνι=ˈçoni,
    καρδιά=karˈðʝa, ποιος=pços; stressed i stays: δύο=ˈðio); primary stress ˈ placed by an
    onset-maximization heuristic (muta-cum-liquida, s-clusters, fricative+stop φτ kept together;
    prenasalized cluster = one onset; diphthong-coda f excluded). Japanese (hiragana): gojūon
    with allophony (u=ɯ r=ɾ し=ɕi ち=t͡ɕi つ=t͡sɯ は=ha ひ=çi ふ=ɸɯ に=ɲi, ざ-row fricatives),
    sokuon っ geminates next C (はっぱ=happa), moraic ん place-assimilates (おんな=onna)/=ɴ finally,
    bare-vowel length (おおきい=oːkiː). Embedded self-test: 65 gold forms (`python scripts/native_g2p.py`).
    Review: `data/normalized/ipa_native_review.tsv`. DOCUMENTED limits: Greek medial μπ/ντ/γκ
    keep the nasal (careful reading; casual denasalizes); λ/ν palatalized only via synizesis;
    Japanese ざ-row not word-initially affricated (none occur), pitch accent not marked.
  - [x] Tier 2 Russian + Bulgarian Cyrillic G2P. DONE: `scripts/cyrillic_g2p.py` (rule-based,
    mirrors slavic_g2p), called from to_ipa.py as method `cyrillic_g2p`. Converts all 433 Cyrillic
    records (rus 226 + bul 207), ALL high-confidence, ZERO residuals. BROAD PHONEMIC, NO vowel
    reduction: none of these lists mark stress, and Russian/Bulgarian akanye/ikanye is
    stress-dependent -> not recoverable, deliberately not applied (it's allophonic noise for
    cross-list comparison anyway). Everything recoverable from spelling IS done: palatalization
    (Cʲ before soft vowels/ь; hard л=ɫ vs soft lʲ; ж ш ц always hard, ч щ always soft),
    iotation (я/е/ё/ю -> Cʲ+V after a consonant, j+V initially/after vowel/ъ/ь), regressive
    voicing assimilation + final devoicing (зуб->zup, водка->votka, сделать->zdʲeɫatʲ; в a target
    not a trigger). Per-language: ru ж/ш=ʐ/ʂ ч=t͡ɕ щ=ɕː ы=ɨ, ъ silent; bg ъ=ɤ (a vowel!) о=ɔ е=ɛ,
    palatalization only before я/ю/ь (ден=dɛn), щ=ʃt, дж/дз digraphs, ж/ш/ч=ʒ/ʃ/t͡ʃ. Per-record
    gating via is_cyrillic() routes only the Cyrillic line (rus/bul interleave a romanized Latin
    synonym line, left unconverted: 74 rus + ~195 bul). Embedded self-test: 49 gold forms
    (`python scripts/cyrillic_g2p.py`). Review: `data/normalized/ipa_cyrillic_review.tsv`.
    DEFERRED: mdf (Moksha, Uralic) -- different palatalization, reduced vowel, voiceless
    sonorants; needs language-specific rules + verification (194 records still deferred_native).
  - [x] Tier 2 romanization-line lists (arb + tha). DONE: `scripts/romanize.py`, called from
    to_ipa.py as method `romanization`. These native-script lists ship a Latin/IPA romanization
    per gloss; converting THAT line sidesteps the script (and tha's mojibake). 309 records, all
    high-confidence (1 residual = the one mojibake tha record). arb (Standard Arabic): the
    romanization is ALREADY full IPA (kullu, ramaːdun, batˁnun, ʕusˁfuːratun) -> pass through,
    only folding tie-less affricates ʤ->d͡ʒ. tha (Thai): Latin + 2-digit Chao tone numbers ->
    digraphs th/kh/ph/ch/ng -> tʰ/kʰ/pʰ/t͡ɕʰ/ŋ, vowels å/æ/y/ø -> ɔ/ɛ/ɯ/ɤ, ':' -> ː, tone digits
    -> Chao tone letters (5->˥..1->˩), e.g. khi:41thau41 -> kʰiː˦˩tʰau˦˩. Syllables self-delimit
    (each ends in its tone digits). Per-record is_latin_line() routes only the romanization line;
    the 224 Thai-script + 128 Arabic-script records stay deferred. Chao tone letters added to
    ipa_features MODS. Embedded self-test: 19 gold forms. Review: ipa_romanization_review.tsv.
  - [x] Tier 2 Mandarin (cmn) Hanzi -> pinyin -> IPA. DONE: curated dict
    `metadata/cmn_hanzi_pinyin.tsv` (101 Hanzi -> pinyin, the lexical step a bare-Hanzi list
    lacks) + `scripts/pinyin_g2p.py` (the deterministic pinyin->IPA engine), method `cmn` in
    to_ipa.py. All 101 records, high-confidence, ZERO residuals. pinyin_g2p handles the spelling
    quirks: zero-initial y/w -> i/u glide, j/q/x+u -> ü, iu/ui/un -> iou/uei/uen, b/p/m/f+o -> uo,
    apical -i after zh/ch/sh/r -> ɻ̩ and after z/c/s -> ɹ̩; tones 1-4 -> Chao letters (˥ ˧˥ ˨˩˦
    ˥˩), neutral unmarked; affricates tie-barred (zh=ʈ͡ʂ). Embedded self-test: 27 gold forms.
    Review: ipa_cmn_review.tsv. (全部->t͡ɕʰɥɛn˧˥pu˥˩, 血->ɕɥe˥˩, 死->sɹ̩˨˩˦, 我们->wo˨˩˦mən.)
  - Tier 2 REMAINING native scripts (4 lists):
    * ydd (Yiddish, Hebrew script, 209 recs): TRACTABLE -- YIVO writes vowels (אַ=a ע=e ו=u/o
      י=i, digraphs וו=v יי=ej וי=oj טש=t͡ʃ זש=ʒ). Wrinkle: loshn-koydesh (Hebrew-origin) words
      like חיה 'animal'=/xaje/ are spelled consonantally, NOT phonetically -> flag those as
      residual. Needs a Hebrew-script (RTL, final forms ך ם ן ף ץ) G2P module. <- DO NEXT.
    * mdf (Moksha Cyrillic, 194 recs): doable by extending cyrillic_g2p, BUT needs Moksha-specific
      verification first -- does it have final devoicing (Uralic, probably NOT, unlike Russian)?
      я=ä vs ja? the reduced vowel ə? voiceless sonorants? Don't ship a Russian-shaped guess.
    * pbt (Pashto) + pes (Farsi) Arabic-SCRIPT, and the arb/pbt Arabic-script lines: true abjads,
      short vowels unwritten (pes has partial harakat). Consonantal skeleton only -> low value;
      needs a lexicon / epitran-style tool. DEFER.
  - Tier 3 Latin orthography + light_ipa (~570): low-resource langs, no off-the-shelf G2P.
    Leverage the TEMPLATE/source clustering (same fieldwork source shares orthography conventions
    -> per-source rule sets convert many at once). Emit confidence; full narrow-IPA not achievable
    for all.
CROSS-CUTTING: anchor to external gold IPA (ASJP - coarse 41-symbol alphabet built for exactly
  this; also Lexibank/CLDF, NorthEuraLex, PHOIBLE) to validate/borrow. STRONG OPTION: do
  cross-list comparison in an ASJP-style sound-class alphabet (collapses IPA vs Americanist vs
  orthography, robust to noise) rather than chasing perfect narrow IPA for 570 orthographic lists.
DATA-QUALITY NOTE (seen during audit, for the cleanup tier): stray '\' in transcriptions
  (Afar "kul\li"), '/' as variant separator ("tambi/tabekobe"), and "(...)"/"[...]" optional
  material ("(ban-)[dum]") -- parse/strip these when tokenizing.

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
  * `й` (U+0439, Cyrillic short-i) — in Latin-script lists (puo etc.) it's a /j/ confusable, BUT
    in the genuinely Cyrillic-script lists (**rus/bul/mdf**) it is a real letter. A blanket й->j
    would CORRUPT those. RESOLVED (Next steps #4): normalize.py now maps й->j (and the Greek-for-
    IPA confusables) under a PER-LINE Latin-dominance gate, so genuine Cyrillic lines are
    untouched. 94 й mapped; see `metadata/confusables_report.tsv`.

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
