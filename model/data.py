"""Pure-python data layer: turn the IPA layer into (language, concept, feature-seq)
training examples, and build the categorical vocabularies.

Torch-free on purpose -- the vocab + feature-extraction logic is the part most
worth unit-testing, and it should not require torch to import. The torch Dataset
/ LightningDataModule live in model.datamodule and call into here.

A training example is `(language, concept, [segment, ...])` where:
  - language = list identifier (doculect),  concept = canonical gloss,
  - each segment = a dict of categorical FIELDS (the 'vocal features').
The decoder predicts these fields per step; padded/boundary positions are
represented as segments whose `type` is a special token and every other field NA.
"""
from __future__ import annotations

import collections
import json
import os
import pickle
import random

# Per-segment categorical fields the model reproduces. Consonant fields and vowel
# fields are disjoint; the inapplicable ones take NA, so every segment fills all
# fields (a clean fixed-width multi-head target).
# 'kind' (consonant/vowel/special), not 'type' -- nn.Module reserves the .type attr.
FIELDS = ["kind", "manner", "place", "voice", "height", "backness", "rounding",
          "length", "nasal"]
PAD, BOS, EOS, NA = "<pad>", "<bos>", "<eos>", "<na>"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_IPA = os.path.join(ROOT, "data", "normalized", "ipa.jsonl")


def seg_to_fields(seg):
    """An ipa_features segment dict -> {field: value} (NA where not applicable)."""
    t = seg.get("type", "unknown")
    f = dict.fromkeys(FIELDS, NA)
    if t == "consonant":
        f["kind"] = "consonant"
        f["voice"] = seg.get("voice", NA)
        f["place"] = seg.get("place", NA)
        f["manner"] = seg.get("manner", NA)
        f["length"] = seg["length"] if seg.get("length") in ("long", "half-long") else "short"
        f["nasal"] = "yes" if seg.get("nasalized") else "no"
    elif t == "vowel":
        f["kind"] = "vowel"
        f["height"] = seg.get("height", NA)
        f["backness"] = seg.get("backness", NA)
        f["rounding"] = seg.get("rounding", NA)
        f["length"] = seg["length"] if seg.get("length") in ("long", "half-long") else "short"
        f["nasal"] = "yes" if seg.get("nasalized") else "no"
    else:
        f["kind"] = "unknown"
    return f


def special_fields(tok):
    """A boundary/pad segment. PAD is all-PAD (so a zero tensor == padding and the
    embedding padding_idx zeroes it); BOS/EOS carry `type` = tok, every field else NA."""
    if tok == PAD:
        return dict.fromkeys(FIELDS, PAD)
    f = dict.fromkeys(FIELDS, NA)
    f["kind"] = tok
    return f


class FieldVocab:
    """Bijection value <-> index for one field. PAD is reserved at index 0 so that
    zero-padded tensors and the embedding `padding_idx` agree."""

    def __init__(self):
        self.itos = []
        self.stoi = {}

    def add(self, v):
        if v not in self.stoi:
            self.stoi[v] = len(self.itos)
            self.itos.append(v)
        return self.stoi[v]

    def get(self, v):
        return self.stoi.get(v, self.stoi[NA])

    def __len__(self):
        return len(self.itos)


def build_vocabs(examples):
    """Build (field_vocabs, lang_vocab, concept_vocab) from a list of examples.
    PAD=0 and NA=1 in every field; type also carries BOS/EOS/unknown."""
    fvocab = {k: FieldVocab() for k in FIELDS}
    for k in FIELDS:
        fvocab[k].add(PAD)
        fvocab[k].add(NA)
    for tok in (BOS, EOS, "unknown"):
        fvocab["kind"].add(tok)
    lang, concept = {}, {}
    for lang_s, concept_s, segs in examples:
        lang.setdefault(lang_s, len(lang))
        concept.setdefault(concept_s, len(concept))
        for sd in segs:
            for k in FIELDS:
                fvocab[k].add(sd[k])
    return fvocab, lang, concept


def encode(example, fvocab, lang_vocab, concept_vocab):
    """One example -> (lang_idx, concept_idx, [tuple-of-field-idx per segment])."""
    lang_s, concept_s, segs = example
    rows = [tuple(fvocab[k].get(sd[k]) for k in FIELDS) for sd in segs]
    return lang_vocab[lang_s], concept_vocab[concept_s], rows


def special_tuples(fvocab):
    """(bos, eos, pad) as field-index tuples for the collate function."""
    def tup(tok):
        sf = special_fields(tok)
        return tuple(fvocab[k].get(sf[k]) for k in FIELDS)
    return tup(BOS), tup(EOS), tup(PAD)


def dedup_cells(examples):
    """One example per (language, concept) cell, first wins. The corpus folds
    several surface glosses to one canonical concept, so a language can carry the
    same cell twice (thou/you -> 'you (singular)') -- keeping both would split
    near-identical forms across train/val (leakage)."""
    seen, out = set(), []
    for ex in examples:
        key = (ex[0], ex[1])
        if key not in seen:
            seen.add(key)
            out.append(ex)
    return out


def split_examples(examples, val_frac=0.05, test_frac=0.0, seed=0):
    """Guarded, language-stratified train/val/test split of (language, concept) cells.

    The model is pure embedding lookups, so it has NO inductive path to an unseen
    language or concept (their embeddings would stay at random init). Hence the
    only well-posed holdout is CELL completion: hold out ~val_frac (+ ~test_frac)
    of each language's cells, but never the last cell of a language and never the
    last train instance of a concept -- so every held cell's language AND concept
    remain observed in train. Assumes deduped examples. Returns (train, val, test)
    (test is empty when test_frac == 0)."""
    by_lang = collections.defaultdict(list)
    for ex in examples:
        by_lang[ex[0]].append(ex)
    concept_train = collections.Counter(ex[1] for ex in examples)   # decremented as we hold out
    rng = random.Random(seed)
    train, val, test = [], [], []
    for lang in sorted(by_lang):
        cells = by_lang[lang][:]
        rng.shuffle(cells)
        n = len(cells)
        n_val = int(n * val_frac)
        n_test = int(n * test_frac)
        if n_val + n_test > n - 1:                  # always keep >=1 cell in train
            n_test = max(0, n - 1 - n_val)
        hv = ht = 0
        for ex in cells:
            c = ex[1]
            if hv < n_val and concept_train[c] > 1:
                val.append(ex); hv += 1; concept_train[c] -= 1
            elif ht < n_test and concept_train[c] > 1:
                test.append(ex); ht += 1; concept_train[c] -= 1
            else:
                train.append(ex)
    if not val and len(train) > 1:          # degenerate tiny input: force a non-empty val
        val.append(train.pop())
    return train, val, test


def load_examples(path=DEFAULT_IPA, segments_fn=None, limit=None, max_len=32):
    """Read the IPA layer (ipa.jsonl) into examples. language = identifier,
    concept = canonical_gloss (fallback gloss); the form is the FIRST comma-
    alternant, segmented by `segments_fn` (defaults to scripts/ipa_features)."""
    if segments_fn is None:
        segments_fn = _default_segments_fn()
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if limit is not None and len(out) >= limit:
                break
            r = json.loads(line)
            ipa = r.get("ipa")
            if not ipa:
                continue
            form = ipa.split(",")[0].strip()
            if not form:
                continue
            segs = [seg_to_fields(s) for s in segments_fn(form)[:max_len]]
            if not segs:
                continue
            concept = r.get("canonical_gloss") or r.get("gloss") or ""
            out.append((r["identifier"], concept, segs))
    return out


def _default_segments_fn():
    """Bridge to the existing tokenizer in scripts/ipa_features.py."""
    import sys
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import ipa_features
    return ipa_features.segments


# --- encoded-tensor cache -----------------------------------------------------
# Re-segmenting the whole corpus (~286k pure-python tokenizations) dominates setup.
# Cache the deduped + integer-encoded examples as compact numpy arrays (CSR layout:
# all segment rows concatenated + per-example lengths) alongside the vocabularies.
# The train/val SPLIT stays at runtime, so val_frac/seed remain live knobs. The
# cache key signs the data file + max_len + the code that produces segments/fields,
# so it auto-invalidates when any of those change.

CACHE_VERSION = 1


def _stat_sig(path):
    try:
        st = os.stat(path)
        return f"{os.path.basename(path)}:{st.st_size}:{int(st.st_mtime)}"
    except OSError:
        return f"{os.path.basename(path)}:missing"


def cache_signature(path, max_len):
    """Signs data file + max_len + the segmenter/feature code (so editing the
    tokenizer or FIELDS invalidates the cache automatically)."""
    code = ";".join(_stat_sig(p) for p in
                    (os.path.join(ROOT, "scripts", "ipa_features.py"),
                     os.path.abspath(__file__)))
    return f"v{CACHE_VERSION}|{_stat_sig(path)}|max_len={max_len}|{code}"


def default_cache_path(path, max_len):
    return os.path.join(os.path.dirname(path), f".cache_encoded_maxlen{max_len}.pkl")


def _vocab_from_itos(itos):
    fv = FieldVocab()
    fv.itos = list(itos)
    fv.stoi = {s: i for i, s in enumerate(fv.itos)}
    return fv


def _encode_all(path, limit, max_len):
    """Slow path: load + segment + dedup + build vocabs + encode."""
    examples = dedup_cells(load_examples(path, limit=limit, max_len=max_len))
    fvocab, lang_vocab, concept_vocab = build_vocabs(examples)
    encoded = [encode(ex, fvocab, lang_vocab, concept_vocab) for ex in examples]
    return fvocab, lang_vocab, concept_vocab, encoded


def _to_arrays(encoded):
    """Encoded examples -> (lang, concept, lengths, rows) numpy arrays (CSR)."""
    import numpy as np
    nf = len(FIELDS)
    n = len(encoded)
    lang = np.fromiter((e[0] for e in encoded), dtype=np.int32, count=n)
    concept = np.fromiter((e[1] for e in encoded), dtype=np.int32, count=n)
    lengths = np.fromiter((len(e[2]) for e in encoded), dtype=np.int32, count=n)
    flat = [x for e in encoded for tup in e[2] for x in tup]
    rows = (np.array(flat, dtype=np.int16).reshape(-1, nf) if flat
            else np.zeros((0, nf), dtype=np.int16))
    return lang, concept, lengths, rows


def _load_or_build_cache(path, max_len, cache_path=None, rebuild=False, verbose=False):
    cp = cache_path or default_cache_path(path, max_len)
    sig = cache_signature(path, max_len)
    if not rebuild and os.path.exists(cp):
        try:
            with open(cp, "rb") as f:
                blob = pickle.load(f)
            if blob.get("sig") == sig:
                fvocab = {k: _vocab_from_itos(v) for k, v in blob["fvocab"].items()}
                return (fvocab, blob["lang"], blob["concept"], blob["lang_arr"],
                        blob["concept_arr"], blob["lengths"], blob["rows"], "cache(hit)")
            if verbose:
                print("cache signature changed; rebuilding")
        except Exception as e:                       # corrupt/old cache -> rebuild
            if verbose:
                print(f"cache read failed ({e}); rebuilding")
    fvocab, lang_vocab, concept_vocab, encoded = _encode_all(path, None, max_len)
    lang_arr, concept_arr, lengths, rows = _to_arrays(encoded)
    blob = {"sig": sig, "fvocab": {k: v.itos for k, v in fvocab.items()},
            "lang": lang_vocab, "concept": concept_vocab, "lang_arr": lang_arr,
            "concept_arr": concept_arr, "lengths": lengths, "rows": rows}
    tmp = cp + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(blob, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, cp)
    return (fvocab, lang_vocab, concept_vocab, lang_arr, concept_arr, lengths, rows,
            "cache(miss->built)")


def encoded_arrays(path=DEFAULT_IPA, records=None, limit=None, max_len=32,
                   cache_path=None, use_cache=True, rebuild=False, verbose=False):
    """Deduped, integer-encoded corpus as numpy arrays + vocabs. Uses the on-disk
    cache for the full corpus; bypasses it for in-memory `records` or a `limit`
    (partial data). Returns (fvocab, lang_vocab, concept_vocab, lang, concept,
    lengths, rows, source)."""
    if records is not None:
        examples = dedup_cells(records)
        fvocab, lang_vocab, concept_vocab = build_vocabs(examples)
        encoded = [encode(e, fvocab, lang_vocab, concept_vocab) for e in examples]
        return (fvocab, lang_vocab, concept_vocab, *_to_arrays(encoded), "records")
    if use_cache and limit is None:
        return _load_or_build_cache(path, max_len, cache_path, rebuild, verbose)
    fvocab, lang_vocab, concept_vocab, encoded = _encode_all(path, limit, max_len)
    return (fvocab, lang_vocab, concept_vocab, *_to_arrays(encoded),
            f"build(limit={limit})")


# --- synthetic data: lets the full pipeline be smoke-tested with no corpus -----

_PALETTE = [
    {"type": "consonant", "voice": "voiceless", "place": "bilabial", "manner": "plosive"},
    {"type": "consonant", "voice": "voiceless", "place": "alveolar", "manner": "plosive"},
    {"type": "consonant", "voice": "voiceless", "place": "velar", "manner": "plosive"},
    {"type": "consonant", "voice": "voiced", "place": "alveolar", "manner": "nasal"},
    {"type": "consonant", "voice": "voiced", "place": "bilabial", "manner": "nasal"},
    {"type": "consonant", "voice": "voiceless", "place": "glottal", "manner": "fricative"},
    {"type": "vowel", "height": "open", "backness": "front", "rounding": "unrounded"},
    {"type": "vowel", "height": "close", "backness": "front", "rounding": "unrounded"},
    {"type": "vowel", "height": "close", "backness": "back", "rounding": "rounded"},
    {"type": "vowel", "height": "close-mid", "backness": "back", "rounding": "rounded",
     "length": "long"},
]


def synthetic_records(n=300, n_lang=12, n_concept=20, seed=0):
    """Random (language, concept, feature-seq) examples for the smoke test."""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        lang = f"lang{rng.randrange(n_lang)}"
        concept = f"concept{rng.randrange(n_concept)}"
        segs = [seg_to_fields(rng.choice(_PALETTE)) for _ in range(rng.randint(2, 6))]
        out.append((lang, concept, segs))
    return out


# --- minimal self-test (torch-free) -------------------------------------------

def _selftest():
    fails = 0
    recs = synthetic_records(50, n_lang=5, n_concept=7, seed=1)
    fvocab, lang, concept = build_vocabs(recs)
    # PAD/NA invariants
    for k in FIELDS:
        if fvocab[k].itos[0] != PAD or fvocab[k].itos[1] != NA:
            fails += 1
            print(f"FAIL field {k}: idx0/1 not PAD/NA")
    bos, eos, pad = special_tuples(fvocab)
    if pad != tuple([0] * len(FIELDS)):
        fails += 1
        print(f"FAIL pad tuple {pad} != all-zero")
    if bos[0] == pad[0] or eos[0] == pad[0]:
        fails += 1
        print("FAIL bos/eos type collides with pad")
    li, ci, rows = encode(recs[0], fvocab, lang, concept)
    if not (0 <= li < len(lang) and 0 <= ci < len(concept) and len(rows[0]) == len(FIELDS)):
        fails += 1
        print("FAIL encode shape")
    # field-extraction sanity: a vowel has NA place, a consonant has NA height
    v = seg_to_fields({"type": "vowel", "height": "open", "backness": "front",
                       "rounding": "unrounded"})
    c = seg_to_fields({"type": "consonant", "voice": "voiced", "place": "velar",
                       "manner": "plosive"})
    if v["place"] != NA or c["height"] != NA or v["kind"] != "vowel":
        fails += 1
        print("FAIL seg_to_fields applicability")

    # guarded 3-way split: no cold-start, partitions disjoint, deduped
    deduped = dedup_cells(synthetic_records(600, n_lang=15, n_concept=25, seed=2))
    train, val, test = split_examples(deduped, val_frac=0.1, test_frac=0.1, seed=2)
    train_cells = {(e[0], e[1]) for e in train}
    val_cells = {(e[0], e[1]) for e in val}
    test_cells = {(e[0], e[1]) for e in test}
    train_langs = {e[0] for e in train}
    train_concepts = {e[1] for e in train}
    if train_cells & val_cells or train_cells & test_cells or val_cells & test_cells:
        fails += 1
        print("FAIL split: partitions overlap")
    if not val or not test:
        fails += 1
        print("FAIL split: empty val/test")
    cold = [(e[0], e[1]) for e in (val + test)
            if e[0] not in train_langs or e[1] not in train_concepts]
    if cold:
        fails += 1
        print(f"FAIL split: {len(cold)} cold-start held cells (lang/concept not in train)")
    if len(dedup_cells(deduped)) != len(deduped):
        fails += 1
        print("FAIL dedup not idempotent")

    # encoded <-> CSR-array round-trip (the layout the array-backed Dataset slices)
    import numpy as np
    fv2, lv2, cv2 = build_vocabs(deduped)
    enc = [encode(ex, fv2, lv2, cv2) for ex in deduped]
    la, ca, lengths, rows = _to_arrays(enc)
    offsets = np.empty(len(la) + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(lengths, out=offsets[1:])
    recon = [(int(la[k]), int(ca[k]),
              [tuple(r) for r in rows[offsets[k]:offsets[k + 1]].tolist()])
             for k in range(len(la))]
    if recon != enc:
        fails += 1
        print("FAIL encoded<->arrays round-trip")
    print(f"data self-test: {'OK' if not fails else str(fails) + ' FAILED'} "
          f"({len(lang)} langs, {len(concept)} concepts, kind-vocab={len(fvocab['kind'])}; "
          f"split {len(train)}/{len(val)}/{len(test)} train/val/test, no cold-start)")
    return fails


if __name__ == "__main__":
    import sys
    sys.exit(1 if _selftest() else 0)
