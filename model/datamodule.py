"""LightningDataModule + Dataset + collate for the conditional vocalic decoder.

Wraps the pure logic in model.data with torch tensors. The collate builds, per
batch, the teacher-forcing pair:
    decoder input  = [BOS] + segments
    decoder target = segments + [EOS]
as one (B, T) long tensor per FIELD, plus a (B, T) mask of real target positions.
"""
from __future__ import annotations

import pytorch_lightning as pl
import torch
from torch.utils.data import DataLoader, Dataset

from model import data
from model.data import FIELDS


class _ArrayDataset(Dataset):
    """Array-backed (CSR) dataset: holds the shared encoded arrays and a subset of
    example indices (a train or val split). Slices a segment block per item."""

    def __init__(self, arrays, index):
        self.lang, self.concept, self.offsets, self.lengths, self.rows = arrays
        self.index = index

    def __len__(self):
        return len(self.index)

    def __getitem__(self, i):
        k = self.index[i]
        o, e = int(self.offsets[k]), int(self.offsets[k + 1])
        segs = [tuple(r) for r in self.rows[o:e].tolist()]
        return int(self.lang[k]), int(self.concept[k]), segs


def make_collate(bos, eos, pad):
    """Collate encoded examples into padded per-field tensors + a target mask."""
    nf = len(FIELDS)

    def collate(batch):
        B = len(batch)
        T = max(len(segs) + 1 for _, _, segs in batch)      # +1 for BOS/EOS
        lang = torch.tensor([l for l, _, _ in batch], dtype=torch.long)
        concept = torch.tensor([c for _, c, _ in batch], dtype=torch.long)
        in_f = {f: torch.zeros(B, T, dtype=torch.long) for f in FIELDS}   # 0 == PAD
        tgt_f = {f: torch.zeros(B, T, dtype=torch.long) for f in FIELDS}
        mask = torch.zeros(B, T, dtype=torch.bool)
        for b, (_, _, segs) in enumerate(batch):
            inp = [bos] + segs
            tgt = segs + [eos]
            for t, (itup, ttup) in enumerate(zip(inp, tgt)):
                for fi, f in enumerate(FIELDS):
                    in_f[f][b, t] = itup[fi]
                    tgt_f[f][b, t] = ttup[fi]
                mask[b, t] = True
        return {"lang": lang, "concept": concept, "in": in_f, "tgt": tgt_f, "mask": mask}

    return collate


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
        self.collate = make_collate(self.bos, self.eos, self.pad)
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
