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


class _SeqDataset(Dataset):
    def __init__(self, encoded):
        self.encoded = encoded            # list of (lang_idx, concept_idx, [field-tuple,...])

    def __len__(self):
        return len(self.encoded)

    def __getitem__(self, i):
        return self.encoded[i]


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
                 val_frac=0.05, limit=None, max_len=32, seed=0, num_workers=0):
        super().__init__()
        self.path = path
        self.records = records
        self.batch_size = batch_size
        self.val_frac = val_frac
        self.limit = limit
        self.max_len = max_len
        self.seed = seed
        self.num_workers = num_workers
        self._ready = False

    def setup(self, stage=None):
        if self._ready:
            return
        examples = self.records if self.records is not None else \
            data.load_examples(self.path, limit=self.limit, max_len=self.max_len)
        if not examples:
            raise RuntimeError(f"no examples loaded from {self.path}")
        examples = data.dedup_cells(examples)
        # vocab over the full (deduped) set so every language/concept has a slot
        self.fvocab, self.lang_vocab, self.concept_vocab = data.build_vocabs(examples)
        train_ex, val_ex = data.split_examples(examples, self.val_frac, self.seed)
        enc = lambda exs: [data.encode(e, self.fvocab, self.lang_vocab, self.concept_vocab)
                           for e in exs]
        self.train_enc, self.val_enc = enc(train_ex), enc(val_ex)
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

    def _loader(self, enc, shuffle):
        return DataLoader(_SeqDataset(enc), batch_size=self.batch_size, shuffle=shuffle,
                          collate_fn=self.collate, num_workers=self.num_workers)

    def train_dataloader(self):
        return self._loader(self.train_enc, True)

    def val_dataloader(self):
        return self._loader(self.val_enc, False)
