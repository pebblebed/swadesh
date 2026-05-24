"""Relatedness probe: does the learned z_language geometry reflect phonetic
relatedness?

Reconstruction val-loss can fall while z_language encodes inventory/phonotactics
rather than genealogy, so relatedness is checked EXTERNALLY: compare pairwise
distances in the language embedding against ASJP-based string distances (LDN over
shared concepts) computed from our own ASJP layer -- the anchor of notes/asjp.html.
Self-contained: reads data/normalized/asjp.jsonl, no external download.

Reported:
  - Spearman rank correlation between z-distance and ASJP-LDN over language pairs
    (the headline: higher = the embedding tracks phonetic relatedness);
  - a same-ISO-code control (doculects of the same language should be each other's
    nearest z-neighbour);
  - a concrete Polynesian read-out (z-distance vs LDN among rap/tah/smo/ton/...).

`uv run python -m model.eval --selftest`            # math self-test only
`uv run python -m model.eval --limit 40000 --epochs 3`   # quick train, then probe
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
ASJP_JSONL = os.path.join(ROOT, "data", "normalized", "asjp.jsonl")

POLYNESIAN = ["rap", "tah", "smo", "ton", "haw", "mri", "mao", "fij", "mri"]


# --- string distance ----------------------------------------------------------

def levenshtein(a, b):
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def ldn(a, b):
    """Levenshtein distance normalized by the longer length (0 = identical)."""
    m = max(len(a), len(b))
    return 0.0 if m == 0 else levenshtein(a, b) / m


def spearman(x, y):
    """Spearman rank correlation (ties broken by order; fine for ~continuous data)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 2:
        return float("nan")

    def rank(v):
        order = np.argsort(v, kind="mergesort")
        r = np.empty(len(v), float)
        r[order] = np.arange(len(v))
        return r
    return float(np.corrcoef(rank(x), rank(y))[0, 1])


# --- ASJP layer ---------------------------------------------------------------

def load_asjp_by_lang(path=ASJP_JSONL):
    """identifier -> {concept: asjp_string} (first form per cell)."""
    by_lang = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            asjp = r.get("asjp")
            if not asjp:
                continue
            concept = r.get("canonical_gloss") or r.get("gloss") or ""
            d = by_lang.setdefault(r["identifier"], {})
            d.setdefault(concept, asjp)
    return by_lang


def _code(identifier):
    """ISO 639-3 code from a Rosetta identifier (rosettaproject_<code>_swadesh-N)."""
    parts = identifier.split("_")
    return parts[1] if len(parts) > 2 else identifier


# --- the probe ----------------------------------------------------------------

def relatedness_report(z, lang_vocab, asjp_path=ASJP_JSONL, top_k=150,
                       min_shared=20, verbose=True):
    """z: (n_lang, d) array; lang_vocab: identifier -> row index. Returns a dict."""
    by_lang = load_asjp_by_lang(asjp_path)
    # languages the model knows AND that have enough ASJP coverage
    cand = [(len(by_lang[l]), l) for l in lang_vocab if l in by_lang
            and len(by_lang[l]) >= min_shared]
    cand.sort(reverse=True)
    langs = [l for _, l in cand[:top_k]]
    if len(langs) < 3:
        if verbose:
            print(f"relatedness: too few covered languages ({len(langs)})")
        return {"rho": float("nan"), "n_lang": len(langs), "n_pairs": 0}

    forms = [by_lang[l] for l in langs]
    rows = [lang_vocab[l] for l in langs]
    ldn_vals, z_vals, pairs = [], [], []
    for i in range(len(langs)):
        fi = forms[i]
        for j in range(i + 1, len(langs)):
            shared = fi.keys() & forms[j].keys()
            if len(shared) < min_shared:
                continue
            d = np.mean([ldn(fi[c], forms[j][c]) for c in shared])
            ldn_vals.append(d)
            z_vals.append(float(np.linalg.norm(z[rows[i]] - z[rows[j]])))
            pairs.append((i, j))
    rho = spearman(ldn_vals, z_vals)

    # same-ISO-code control: of doculects whose code repeats in the set, how often
    # is the nearest z-neighbour a same-code doculect?
    codes = [_code(l) for l in langs]
    code_groups = {}
    for k, c in enumerate(codes):
        code_groups.setdefault(c, []).append(k)
    repeated = [g for g in code_groups.values() if len(g) > 1]
    nn_hits = nn_tot = 0
    zsub = np.stack([z[r] for r in rows])
    for g in repeated:
        for k in g:
            d = np.linalg.norm(zsub - zsub[k], axis=1)
            d[k] = np.inf
            nn = int(np.argmin(d))
            nn_hits += (codes[nn] == codes[k])
            nn_tot += 1

    if verbose:
        print(f"\n=== relatedness probe ===")
        print(f"languages: {len(langs)} (top by ASJP coverage)   pairs: {len(ldn_vals)}")
        print(f"Spearman rho(z-distance, ASJP-LDN): {rho:+.3f}   "
              f"(0 = no relation; >0 = z tracks phonetic relatedness)")
        if nn_tot:
            print(f"same-code control: {nn_hits}/{nn_tot} doculects' nearest z-neighbour "
                  f"shares the ISO code")
        _polynesian_readout(z, lang_vocab, by_lang, min_shared)
    return {"rho": rho, "n_lang": len(langs), "n_pairs": len(ldn_vals),
            "same_code_hits": nn_hits, "same_code_total": nn_tot}


def _polynesian_readout(z, lang_vocab, by_lang, min_shared):
    sel = []
    for ident, idx in lang_vocab.items():
        if _code(ident) in POLYNESIAN and ident in by_lang:
            sel.append(ident)
    sel = sorted(set(sel))
    if len(sel) < 2:
        return
    print("Polynesian testbed (z-distance | ASJP-LDN):")
    for a in range(len(sel)):
        for b in range(a + 1, len(sel)):
            ia, ib = sel[a], sel[b]
            shared = by_lang[ia].keys() & by_lang[ib].keys()
            if len(shared) < min_shared:
                continue
            zd = float(np.linalg.norm(z[lang_vocab[ia]] - z[lang_vocab[ib]]))
            ld = float(np.mean([ldn(by_lang[ia][c], by_lang[ib][c]) for c in shared]))
            print(f"  {_code(ia):>4}-{_code(ib):<4}  z={zd:6.3f} | ldn={ld:.3f}  (n={len(shared)})")


# --- self-test ----------------------------------------------------------------

def _selftest():
    fails = 0
    if levenshtein("kitten", "sitting") != 3:
        fails += 1
        print("FAIL levenshtein kitten/sitting")
    if levenshtein("abc", "abc") != 0 or abs(ldn("abc", "abxc") - 0.25) > 1e-9:
        fails += 1
        print("FAIL ldn")
    # perfect monotone relation -> rho ~ +1 ; reversed -> ~ -1
    a = [1.0, 2, 3, 4, 5, 6]
    if spearman(a, [2.0, 4, 6, 8, 10, 12]) < 0.999:
        fails += 1
        print("FAIL spearman +1")
    if spearman(a, [6.0, 5, 4, 3, 2, 1]) > -0.999:
        fails += 1
        print("FAIL spearman -1")
    print(f"eval self-test: {'OK' if not fails else str(fails) + ' FAILED'}")
    return fails


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--selftest", action="store_true", help="run math self-test and exit")
    p.add_argument("--limit", type=int, default=None, help="cap #records for the quick train")
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--top-k", type=int, default=150)
    p.add_argument("--min-shared", type=int, default=20)
    p.add_argument("--accelerator", default="auto", help="PTL accelerator: auto|gpu|cpu")
    args = p.parse_args(argv)

    if _selftest():
        return 1
    if args.selftest:
        return 0

    import pytorch_lightning as pl
    import torch
    from model.datamodule import SwadeshDataModule
    from model.decoder import ConditionalVocalicDecoder

    torch.set_float32_matmul_precision("high")
    print("accelerator: " + (f"CUDA - {torch.cuda.get_device_name(0)}"
                             if torch.cuda.is_available() else "CPU"))
    dm = SwadeshDataModule(limit=args.limit, batch_size=128)
    dm.setup()
    print(f"train {len(dm.train_enc)} / val {len(dm.val_enc)} cells; "
          f"{dm.n_lang} languages, {dm.n_concept} concepts")
    model = ConditionalVocalicDecoder(field_sizes=dm.field_sizes, n_lang=dm.n_lang,
                                      n_concept=dm.n_concept)
    tr = pl.Trainer(max_epochs=args.epochs, accelerator=args.accelerator, devices="auto",
                    logger=False, enable_checkpointing=False, enable_model_summary=False,
                    enable_progress_bar=False)
    tr.fit(model, dm)
    print(f"trained on device: {tr.strategy.root_device}")
    z = model.language_embeddings().numpy()
    relatedness_report(z, dm.lang_vocab, top_k=args.top_k, min_shared=args.min_shared)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
