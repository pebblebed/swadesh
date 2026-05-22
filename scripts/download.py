#!/usr/bin/env python3
"""Download the raw Rosetta Project Swadesh-list text files from the Internet Archive.

Idempotent and resumable: files already present in data/raw are skipped, so this
script can be re-run safely on every pass through the OLE loop until the corpus
is complete.

Source collection (1,237 search hits, of which 1,229 are true Swadesh lists):
    https://archive.org/search?query=swadesh+collection%3Arosettaproject

Each archive item `rosettaproject_<code>_swadesh-<N>` contains a `<code>.txt`
file holding the list as `english_gloss: transcription` lines (UTF-8). We save it
locally as `data/raw/<identifier>.txt` so the `-2`/`-3` variants never collide.
"""
import json
import os
import sys
import threading
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "metadata", "manifest.json")
RAW_DIR = os.path.join(ROOT, "data", "raw")
FAIL_LOG = os.path.join(ROOT, "metadata", "download_failures.tsv")
DL = "https://archive.org/download/{ident}/{fname}"
META = "https://archive.org/metadata/{ident}"
UA = "swadesh-corpus-normalizer/0.1 (research; contact kma@pebblebed.com)"


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def discover_txt(ident):
    """Ask the metadata API for the original .txt file name inside an item."""
    meta = json.loads(fetch(META.format(ident=ident)))
    cands = [
        f["name"]
        for f in meta.get("files", [])
        if f["name"].endswith(".txt")
        and not f["name"].endswith("_meta.txt")
        and not f["name"].endswith("_files.txt")
    ]
    return cands[0] if cands else None


WORKERS = 12  # concurrent downloads; archive.org handles this comfortably


def download_one(ident):
    """Return ('done'|'skip', ident, err_or_None). Idempotent per file."""
    code = ident.split("rosettaproject_", 1)[1].rsplit("_swadesh-", 1)[0]
    out = os.path.join(RAW_DIR, ident + ".txt")
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return ("skip", ident, None)
    fname = code + ".txt"
    for attempt in range(2):
        try:
            data = fetch(DL.format(ident=ident, fname=fname))
            tmp = out + ".part"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, out)  # atomic: a partial write never looks complete
            return ("done", ident, None)
        except urllib.error.HTTPError as e:
            if e.code == 404 and attempt == 0:
                real = discover_txt(ident)  # fall back to true file name
                if real:
                    fname = real
                    continue
            return ("fail", ident, f"{fname}\t{e}")
        except Exception as e:  # noqa: BLE001 - log and continue
            return ("fail", ident, f"{fname}\t{e}")


def main():
    docs = json.load(open(MANIFEST, encoding="utf-8"))["response"]["docs"]
    swadesh = [d["identifier"] for d in docs if "_swadesh-" in d["identifier"]]
    os.makedirs(RAW_DIR, exist_ok=True)
    counts = {"done": 0, "skip": 0, "fail": 0}
    failures = []
    lock = threading.Lock()
    n = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(download_one, ident): ident for ident in swadesh}
        for fut in as_completed(futs):
            status, ident, err = fut.result()
            with lock:
                counts[status] += 1
                if err:
                    failures.append((ident, err))
                n += 1
                if n % 100 == 0:
                    print(f"  {n}/{len(swadesh)}  {counts}", flush=True)
    with open(FAIL_LOG, "w", encoding="utf-8") as f:
        for ident, err in failures:
            f.write(f"{ident}\t{err}\n")
    print(f"\nDONE: {counts} total_swadesh={len(swadesh)}")
    if failures:
        print(f"Failures logged to {FAIL_LOG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
