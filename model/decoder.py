"""ConditionalVocalicDecoder -- the LightningModule.

    z_lang    = LanguageEmbedding(language)
    z_concept = ConceptEmbedding(concept)
    cond      = [z_lang ; z_concept]
    LSTM, with (h0, c0) projected from cond and cond concatenated to every step,
    decodes the phonetic form as a sequence of segments. Each segment is predicted
    by a per-FIELD softmax head (the 'vocal features'); the loss is the sum of the
    field cross-entropies over non-pad positions.

Language relatedness is read off `language_embeddings()` (the z_lang matrix) --
the whole point of conditioning the bottleneck this way.
"""
from __future__ import annotations

import pytorch_lightning as pl
import torch
import torch.nn as nn
import torch.nn.functional as F

from model.data import FIELDS

PAD_IDX = 0   # PAD reserved at index 0 in every field vocab (see model.data)


class ConditionalVocalicDecoder(pl.LightningModule):
    def __init__(self, field_sizes, n_lang, n_concept, d_lang=64, d_concept=64,
                 d_in=96, hidden=256, layers=1, dropout=0.1, lr=2e-3):
        super().__init__()
        self.save_hyperparameters()
        self.fields = list(FIELDS)

        self.lang_emb = nn.Embedding(n_lang, d_lang)
        self.concept_emb = nn.Embedding(n_concept, d_concept)
        d_cond = d_lang + d_concept

        # input: sum of per-field embeddings of the previous segment
        self.in_emb = nn.ModuleDict({
            f: nn.Embedding(field_sizes[f], d_in, padding_idx=PAD_IDX) for f in self.fields})

        # cond -> initial (h0, c0); cond is also concatenated to each step's input
        self.h0 = nn.Linear(d_cond, hidden * layers)
        self.c0 = nn.Linear(d_cond, hidden * layers)
        self.lstm = nn.LSTM(d_in + d_cond, hidden, num_layers=layers, batch_first=True,
                            dropout=dropout if layers > 1 else 0.0)

        # one classifier head per field (the multi-head 'vocal feature' target)
        self.heads = nn.ModuleDict({f: nn.Linear(hidden, field_sizes[f]) for f in self.fields})
        self.drop = nn.Dropout(dropout)

    def cond(self, lang_idx, concept_idx):
        return torch.cat([self.lang_emb(lang_idx), self.concept_emb(concept_idx)], dim=-1)

    def forward(self, lang_idx, concept_idx, in_fields):
        B, T = in_fields[self.fields[0]].shape
        cond = self.cond(lang_idx, concept_idx)                      # (B, d_cond)
        x = sum(self.in_emb[f](in_fields[f]) for f in self.fields)   # (B, T, d_in)
        x = torch.cat([self.drop(x), cond.unsqueeze(1).expand(-1, T, -1)], dim=-1)

        layers, hidden = self.hparams.layers, self.hparams.hidden
        h0 = self.h0(cond).view(B, layers, hidden).transpose(0, 1).contiguous()
        c0 = self.c0(cond).view(B, layers, hidden).transpose(0, 1).contiguous()
        out, _ = self.lstm(x, (h0, c0))                              # (B, T, hidden)
        out = self.drop(out)
        return {f: self.heads[f](out) for f in self.fields}         # field -> (B, T, V_f)

    def _step(self, batch, stage):
        logits = self(batch["lang"], batch["concept"], batch["in"])
        m = batch["mask"].float()
        n = m.sum().clamp(min=1.0)
        total = 0.0
        for f in self.fields:
            lg, tg = logits[f], batch["tgt"][f]
            ce = F.cross_entropy(lg.reshape(-1, lg.size(-1)), tg.reshape(-1),
                                 reduction="none").view_as(m)
            total = total + (ce * m).sum() / n
        # train logs a live per-step curve + a per-epoch mean (-> train_loss_step /
        # train_loss_epoch); val/test log a clean per-epoch val_loss / test_loss.
        self.log(f"{stage}_loss", total, prog_bar=True, batch_size=int(m.size(0)),
                 on_step=(stage == "train"), on_epoch=True)
        return total

    def training_step(self, batch, _):
        return self._step(batch, "train")

    def validation_step(self, batch, _):
        return self._step(batch, "val")

    def test_step(self, batch, _):
        return self._step(batch, "test")

    def configure_optimizers(self):
        return torch.optim.Adam(self.parameters(), lr=self.hparams.lr)

    @torch.no_grad()
    def language_embeddings(self):
        """The learned z_language matrix (n_lang, d_lang); relatedness = its distances."""
        return self.lang_emb.weight.detach().cpu()
