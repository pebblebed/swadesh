This is an effort to prepare the Rosetta Project's archive of
Swadesh lists for modern statistical NLP/neural investigation.
Our dream would be to have a discovery of new language historical
information; a more approachable goal might be confirming some
of what is already understood.

TODO.md describes work-in-progress (read it first — it carries findings across loop runs).

Repo layout:
- `scripts/`   — pipeline code (`download.py` so far; idempotent/resumable).
- `data/raw/`  — verbatim `<identifier>.txt` files pulled from the Internet Archive.
- `metadata/`  — `manifest.json` (the archive search result), download logs/failures.

Data provenance: the Rosetta blog post links to the Internet Archive collection
`rosettaproject`; the actual Swadesh `.txt` files are downloaded from there. See
TODO.md "FINDINGS" for the exact source URLs, file format, and known data quirks.
