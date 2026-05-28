#!/usr/bin/env python3
"""Download external reference data into data/external/ (gitignored).

These files are third-party datasets we deliberately do NOT vendor into the
repo: they are large, redownloadable, and carry their own upstream licences and
versioning. The pipeline degrades gracefully when they are absent (the Glottolog
family eval and the CMUdict English G2P both guard on os.path.exists), so this
script is optional — run it when you want those features.

Idempotent and resumable, like scripts/download.py: a file already present in
data/external/ is skipped, and each download is written to a .part temp file and
atomically renamed so an interrupted run never leaves a half-written file.

    python scripts/fetch_external.py            # fetch whatever is missing
    python scripts/fetch_external.py --force     # re-download everything

See AGENTS.md ("External reference data") for provenance, licences, and the
canonical source URLs.
"""
import argparse
import os
import sys
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTERNAL_DIR = os.path.join(ROOT, "data", "external")
UA = "swadesh-corpus-normalizer/0.1 (research; contact kma@pebblebed.com)"

# name -> (url, description). The URLs point at the upstream `master` branch; pin
# a release tag in place of `master` if you need a reproducible snapshot.
RESOURCES = {
    "glottolog_languages.csv": (
        "https://raw.githubusercontent.com/glottolog/glottolog-cldf/master/cldf/languages.csv",
        "Glottolog-CLDF language table (ISO 639-3 -> family); used by the "
        "external relatedness eval in model/eval.py. Licence: CC-BY-4.0.",
    ),
    "cmudict.dict": (
        "https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict",
        "CMU Pronouncing Dictionary (ARPABET); used by the English G2P in "
        "scripts/cmudict_eng.py. Licence: BSD-2-Clause.",
    ),
}


def fetch(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def download_one(name, url, force):
    out = os.path.join(EXTERNAL_DIR, name)
    if not force and os.path.exists(out) and os.path.getsize(out) > 0:
        return ("skip", name, None)
    try:
        data = fetch(url)
        tmp = out + ".part"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, out)  # atomic: a partial write never looks complete
        return ("done", name, f"{len(data):,} bytes")
    except (urllib.error.URLError, OSError) as e:  # noqa: BLE001 - report and continue
        return ("fail", name, str(e))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true",
                    help="re-download even if the file is already present")
    args = ap.parse_args()

    os.makedirs(EXTERNAL_DIR, exist_ok=True)
    failed = False
    for name, (url, _desc) in RESOURCES.items():
        status, _, info = download_one(name, url, args.force)
        detail = f" ({info})" if info else ""
        print(f"  {status:4}  {name}{detail}", flush=True)
        if status == "fail":
            failed = True
            print(f"        source: {url}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
