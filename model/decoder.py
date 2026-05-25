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
                 d_in=96, hidden=256, layers=1, dropout=0.1, lr=2e-3,
                 optimizer="adam", weight_decay=0.0, lr_schedule="none",
                 warmup_frac=0.0, emb_dropout=0.0, label_smoothing=0.0, decoder="lstm"):
        super().__init__()
        self.save_hyperparameters()
        self.fields = list(FIELDS)

        self.lang_emb = nn.Embedding(n_lang, d_lang)
        self.concept_emb = nn.Embedding(n_concept, d_concept)
        d_cond = d_lang + d_concept

        # input: sum of per-field embeddings of the previous segment
        self.in_emb = nn.ModuleDict({
            f: nn.Embedding(field_sizes[f], d_in, padding_idx=PAD_IDX) for f in self.fields})

        # cond -> initial recurrent state; cond is also concatenated to each step's input
        self.h0 = nn.Linear(d_cond, hidden * layers)
        rnn_cls = nn.GRU if decoder == "gru" else nn.LSTM
        self.rnn = rnn_cls(d_in + d_cond, hidden, num_layers=layers, batch_first=True,
                           dropout=dropout if layers > 1 else 0.0)
        if decoder != "gru":                         # LSTM also needs an initial cell state
            self.c0 = nn.Linear(d_cond, hidden * layers)

        # one classifier head per field (the multi-head 'vocal feature' target)
        self.heads = nn.ModuleDict({f: nn.Linear(hidden, field_sizes[f]) for f in self.fields})
        self.drop = nn.Dropout(dropout)
        self.emb_drop = nn.Dropout(emb_dropout)     # dropout on z_lang / z_concept

    def cond(self, lang_idx, concept_idx):
        return torch.cat([self.emb_drop(self.lang_emb(lang_idx)),
                          self.emb_drop(self.concept_emb(concept_idx))], dim=-1)

    def forward(self, lang_idx, concept_idx, in_fields):
        B, T = in_fields[self.fields[0]].shape
        cond = self.cond(lang_idx, concept_idx)                      # (B, d_cond)
        x = sum(self.in_emb[f](in_fields[f]) for f in self.fields)   # (B, T, d_in)
        x = torch.cat([self.drop(x), cond.unsqueeze(1).expand(-1, T, -1)], dim=-1)

        layers, hidden = self.hparams.layers, self.hparams.hidden
        h0 = self.h0(cond).view(B, layers, hidden).transpose(0, 1).contiguous()
        if self.hparams.decoder == "gru":
            out, _ = self.rnn(x, h0)                                 # (B, T, hidden)
        else:
            c0 = self.c0(cond).view(B, layers, hidden).transpose(0, 1).contiguous()
            out, _ = self.rnn(x, (h0, c0))
        out = self.drop(out)
        return {f: self.heads[f](out) for f in self.fields}         # field -> (B, T, V_f)

    def _step(self, batch, stage):
        logits = self(batch["lang"], batch["concept"], batch["in"])
        m = batch["mask"].float()
        n = m.sum().clamp(min=1.0)
        total = 0.0
        # label smoothing on TRAIN only -> val/test stay clean CE, so val_loss is
        # comparable across configs (the beam-search selection metric).
        ls = self.hparams.label_smoothing if stage == "train" else 0.0
        for f in self.fields:
            lg, tg = logits[f], batch["tgt"][f]
            ce = F.cross_entropy(lg.reshape(-1, lg.size(-1)), tg.reshape(-1),
                                 reduction="none", label_smoothing=ls).view_as(m)
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
        hp = self.hparams
        opt_cls = torch.optim.AdamW if hp.optimizer == "adamw" else torch.optim.Adam
        opt = opt_cls(self.parameters(), lr=hp.lr, weight_decay=hp.weight_decay)
        if hp.lr_schedule != "cosine":
            return opt
        import math
        total = int(self.trainer.estimated_stepping_batches)
        warmup = int(total * hp.warmup_frac)

        def lr_lambda(step):
            if step < warmup:
                return (step + 1) / max(1, warmup)
            prog = (step - warmup) / max(1, total - warmup)
            return 0.5 * (1.0 + math.cos(math.pi * min(1.0, prog)))

        sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda)
        return {"optimizer": opt, "lr_scheduler": {"scheduler": sched, "interval": "step"}}

    @torch.no_grad()
    def generate(self, lang_idx, concept_idx, bos_row, eos_kind, kind_pos=0,
                 max_len=24, sample=False, temperature=1.0):
        """Autoregressive decode conditioned on (language, concept). bos_row = the
        BOS segment's field-index tuple; eos_kind = the EOS index in the `kind`
        field (decoding stops when a segment's kind == eos_kind). Returns, per batch
        item, a list of decoded segments (each a tuple of field indices)."""
        was_training = self.training
        self.eval()
        dev = self.lang_emb.weight.device
        lang_idx, concept_idx = lang_idx.to(dev), concept_idx.to(dev)
        B = lang_idx.shape[0]
        cond = torch.cat([self.lang_emb(lang_idx), self.concept_emb(concept_idx)], dim=-1)
        layers, hidden = self.hparams.layers, self.hparams.hidden
        h = self.h0(cond).view(B, layers, hidden).transpose(0, 1).contiguous()
        c = None if self.hparams.decoder == "gru" else \
            self.c0(cond).view(B, layers, hidden).transpose(0, 1).contiguous()
        cur = torch.tensor([list(bos_row)] * B, dtype=torch.long, device=dev)   # (B, n_field)
        outs, done = [[] for _ in range(B)], [False] * B
        for _ in range(max_len):
            x = sum(self.in_emb[f](cur[:, j]) for j, f in enumerate(self.fields))
            x = torch.cat([x, cond], dim=-1).unsqueeze(1)                       # (B, 1, *)
            if self.hparams.decoder == "gru":
                o, h = self.rnn(x, h)
            else:
                o, (h, c) = self.rnn(x, (h, c))
            o = o[:, 0]
            nxt = torch.empty(B, len(self.fields), dtype=torch.long, device=dev)
            for j, f in enumerate(self.fields):
                logit = self.heads[f](o)
                nxt[:, j] = (torch.multinomial(torch.softmax(logit / temperature, -1), 1)[:, 0]
                             if sample else logit.argmax(-1))
            for b in range(B):
                if done[b]:
                    continue
                if int(nxt[b, kind_pos]) == eos_kind:
                    done[b] = True
                else:
                    outs[b].append(tuple(nxt[b].tolist()))
            cur = nxt
            if all(done):
                break
        if was_training:
            self.train()
        return outs

    @torch.no_grad()
    def language_embeddings(self):
        """The learned z_language matrix (n_lang, d_lang); relatedness = its distances."""
        return self.lang_emb.weight.detach().cpu()
