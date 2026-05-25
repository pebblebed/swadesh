"""LightningDataModule + Dataset + collate for the conditional vocalic decoder.

Wraps the pure logic in model.data with torch tensors. The collate builds, per
batch, the teacher-forcing pair:
    decoder input  = [BOS] + segments
    decoder target = segments + [EOS]
as one (B, T) long tensor per FIELD, plus a (B, T) mask of real target positions.
"""
from __future__ import annotations

import functools

import numpy as np
import pytorch_lightning as pl
import torch
from torch.utils.data import DataLoader, Dataset

from model import data
from model.data import FIELDS


class _ArrayDataset(Dataset):
    """Array-backed (CSR) dataset: holds the shared encoded arrays and a subset of
    example indices (a train or val split). Returns a language id, concept id, and
    the example's (n_seg, n_field) int slice -- the collate pads/stacks in bulk."""

    def __init__(self, arrays, index):
        self.lang, self.concept, self.offsets, self.lengths, self.rows = arrays
        self.index = index

    def __len__(self):
        return len(self.index)

    def __getitem__(self, i):
        k = self.index[i]
        o, e = int(self.offsets[k]), int(self.offsets[k + 1])
        return int(self.lang[k]), int(self.concept[k]), self.rows[o:e]


def collate_batch(batch, bos, eos):
    """Vectorized teacher-forcing collate (top-level -> picklable for num_workers>0).
    Builds (B, T, n_field) int arrays in numpy with per-example slice assignment
    (B copies, not B*T*n_field python writes), then views one (B, T) tensor per
    field. input = [BOS]+segs, target = segs+[EOS]; PAD=0; mask marks real positions."""
    nf = len(FIELDS)
    B = len(batch)
    lens = [b[2].shape[0] for b in batch]
    T = max(lens) + 1                                   # +1 for BOS/EOS
    in_arr = np.zeros((B, T, nf), dtype=np.int64)       # 0 == PAD everywhere
    tgt_arr = np.zeros((B, T, nf), dtype=np.int64)
    mask = np.zeros((B, T), dtype=bool)
    lang = np.empty(B, dtype=np.int64)
    concept = np.empty(B, dtype=np.int64)
    bos_a, eos_a = np.asarray(bos, dtype=np.int64), np.asarray(eos, dtype=np.int64)
    for i, (lg, cc, rows) in enumerate(batch):
        L = rows.shape[0]
        lang[i], concept[i] = lg, cc
        in_arr[i, 0] = bos_a
        if L:
            in_arr[i, 1:L + 1] = rows
            tgt_arr[i, :L] = rows
        tgt_arr[i, L] = eos_a
        mask[i, :L + 1] = True
    in_t, tgt_t = torch.from_numpy(in_arr), torch.from_numpy(tgt_arr)
    return {"lang": torch.from_numpy(lang), "concept": torch.from_numpy(concept),
            "in": {f: in_t[:, :, j] for j, f in enumerate(FIELDS)},
            "tgt": {f: tgt_t[:, :, j] for j, f in enumerate(FIELDS)},
            "mask": torch.from_numpy(mask)}


class SwadeshDataModule(pl.LightningDataModule):
    """Either reads the IPA layer (``path``) or uses in-memory ``records``
    (for the smoke test). Vocabularies are built in ``setup`` (idempotent), after
    which ``field_sizes`` / ``n_lang`` / ``n_concept`` size the model."""

    def __init__(self, path=data.DEFAULT_IPA, records=None, batch_size=128,
                 val_frac=0.05, test_frac=0.05, limit=None, max_len=32, seed=0,
                 num_workers=0, use_cache=True):
        super().__init__()
        self.path = path
        self.records = records
        self.batch_size = batch_size
        self.val_frac = val_frac
        self.test_frac = test_frac
        self.limit = limit
        self.max_len = max_len
        self.seed = seed
        self.num_workers = num_workers
        self.use_cache = use_cache
        self._ready = False

    def setup(self, stage=None):
        if self._ready:
            return
        import numpy as np
        (self.fvocab, self.lang_vocab, self.concept_vocab,
         lang, concept, lengths, rows, self.source) = data.encoded_arrays(
            path=self.path, records=self.records, limit=self.limit,
            max_len=self.max_len, use_cache=self.use_cache)
        if len(lang) == 0:
            raise RuntimeError(f"no examples loaded from {self.path}")
        offsets = np.empty(len(lang) + 1, dtype=np.int64)
        offsets[0] = 0
        np.cumsum(lengths, out=offsets[1:])
        arrays = (lang, concept, offsets, lengths, rows)
        # guarded split at runtime over example indices (cells already deduped)
        proxies = [(int(lang[k]), int(concept[k]), k) for k in range(len(lang))]
        train_p, val_p, test_p = data.split_examples(
            proxies, self.val_frac, self.test_frac, self.seed)
        self.train_ds = _ArrayDataset(arrays, [p[2] for p in train_p])
        self.val_ds = _ArrayDataset(arrays, [p[2] for p in val_p])
        self.test_ds = _ArrayDataset(arrays, [p[2] for p in test_p])
        self.bos, self.eos, self.pad = data.special_tuples(self.fvocab)
        self.collate = functools.partial(collate_batch, bos=self.bos, eos=self.eos)
        self._ready = True

    # sizes the model is constructed from
    @property
    def field_sizes(self):
        return {f: len(self.fvocab[f]) for f in FIELDS}

    @property
    def n_lang(self):
        return len(self.lang_vocab)

    @property
    def n_concept(self):
        return len(self.concept_vocab)

    def _loader(self, ds, shuffle):
        return DataLoader(ds, batch_size=self.batch_size, shuffle=shuffle,
                          collate_fn=self.collate, num_workers=self.num_workers,
                          pin_memory=True)

    def train_dataloader(self):
        return self._loader(self.train_ds, True)

    def val_dataloader(self):
        return self._loader(self.val_ds, False)

    def test_dataloader(self):
        return self._loader(self.test_ds, False)
