This is an effort to prepare the Rosetta Project's archive of
Swadesh lists for modern statistical NLP/neural investigation.
Our dream would be to have a discovery of new language historical
information; a more approachable goal might be confirming some
of what is already understood.

TODO.md describes work-in-progress (read it first — it carries findings across loop runs).

Repo layout:
- `scripts/`   — pipeline code (`download.py`, `fetch_external.py`, …; idempotent/resumable).
- `data/raw/`  — verbatim `<identifier>.txt` files pulled from the Internet Archive.
- `data/external/` — third-party reference datasets, gitignored (see below).
- `metadata/`  — `manifest.json` (the archive search result), download logs/failures.

Data provenance: the Rosetta blog post links to the Internet Archive collection
`rosettaproject`; the actual Swadesh `.txt` files are downloaded from there. See
TODO.md "FINDINGS" for the exact source URLs, file format, and known data quirks.

## External reference data (do not commit)

`data/external/` holds third-party datasets we deliberately do **not** copy into
the repo: they are large, redownloadable, carry their own upstream licences, and
have their own versioning, so vendoring a stale copy would muddy provenance. The
whole directory is gitignored. Code that uses these files guards on
`os.path.exists` and degrades gracefully when they are absent, so a fresh clone
runs fine without them.

Fetch them with `python scripts/fetch_external.py` (idempotent — skips files
already present; `--force` re-downloads). Sources:

| File | Source | Licence | Used by |
|------|--------|---------|---------|
| `glottolog_languages.csv` | `https://raw.githubusercontent.com/glottolog/glottolog-cldf/master/cldf/languages.csv` | CC-BY-4.0 | `model/eval.py` external relatedness / family eval |
| `cmudict.dict` | `https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict` | BSD-2-Clause | `scripts/cmudict_eng.py` English G2P |

The URLs track each project's `master` branch; pin a release tag in
`scripts/fetch_external.py` if you need a reproducible snapshot. When adding a
new external dependency, register it in `RESOURCES` in that script and add a row
here rather than committing the file.
