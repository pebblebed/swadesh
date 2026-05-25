"""Subjective eval: train a good config, then decode (language, concept) -> a
phonetic form and show it next to the ground-truth IPA.

The model emits broad FEATURE BUNDLES (the vocal-feature scheme), so we render each
decoded segment back to an approximate IPA symbol via an inverted ipa_features table
(tone / exact narrow detail are not recoverable -- this is a broad reconstruction).
Ground truth is the real first-alternant IPA from data/normalized/ipa.jsonl.

  uv run python -m model.sample                         # Polynesian (tah/rap/smo/ton)
  uv run python -m model.sample --codes tah,rap --epochs 60
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pytorch_lightning as pl  # noqa: E402
import torch  # noqa: E402

import ipa_features as ipf  # noqa: E402  (scripts/)
from model.data import EOS, FIELDS  # noqa: E402
from model.datamodule import SwadeshDataModule  # noqa: E402
from model.decoder import ConditionalVocalicDecoder  # noqa: E402

torch.set_float32_matmul_precision("high")

IPA_JSONL = os.path.join(ROOT, "data", "normalized", "ipa.jsonl")

# inverted feature tables: features -> a representative IPA symbol
CONS_REV = {}
for _sym, _f in ipf.CONS.items():
    CONS_REV.setdefault(_f, _sym)                       # (voice, place, manner) -> symbol
VOW_REV = {}
for _sym, _f in ipf.VOW.items():
    VOW_REV.setdefault(_f, _sym)                        # (height, backness, rounding) -> symbol
AFFR_REV = {
    ("voiceless", "alveolar"): "t͡s", ("voiced", "alveolar"): "d͡z",
    ("voiceless", "postalveolar"): "t͡ʃ", ("voiced", "postalveolar"): "d͡ʒ",
    ("voiceless", "alveolo-palatal"): "t͡ɕ", ("voiced", "alveolo-palatal"): "d͡ʑ",
    ("voiceless", "palatal"): "c", ("voiced", "palatal"): "ɟ",
    ("voiceless", "retroflex"): "ʈ͡ʂ", ("voiced", "retroflex"): "ɖ͡ʐ",
    ("voiceless", "velar"): "k͡x",
}

CONCEPTS = ["water", "fire", "sun", "moon", "star", "stone", "rain",
            "eye", "ear", "tooth", "tongue", "hand", "nose",
            "dog", "bird", "fish", "one", "two", "big", "name"]
DEFAULT_CODES = ["tah", "cmn"]   # Tahitian + Mandarin (note: cmn has only 101 cells; tone not modeled)


def render_seg(seg, fvocab):
    """A decoded segment (field-index tuple) -> approximate IPA symbol ('' if special)."""
    v = {FIELDS[j]: fvocab[FIELDS[j]].itos[seg[j]] for j in range(len(FIELDS))}
    kind = v["kind"]
    if kind == "vowel":
        s = VOW_REV.get((v["height"], v["backness"], v["rounding"]), "ə")
        if v["length"] == "long":
            s += "ː"
        if v["nasal"] == "yes":
            s += "̃"
        return s
    if kind == "consonant":
        m = v["manner"]
        if "lateral" in m and "affricate" in m:
            s = "t͡ɬ" if v["voice"] == "voiceless" else "d͡ɮ"
        elif "affricate" in m:
            s = AFFR_REV.get((v["voice"], v["place"]), "?")
        else:
            s = CONS_REV.get((v["voice"], v["place"], m), "?")
        if v["length"] == "long":
            s += "ː"
        return s
    return ""                                            # bos/eos/pad/unknown


def render_word(segs, fvocab):
    return "".join(render_seg(s, fvocab) for s in segs) or "∅"


def load_ground_truth():
    """identifier -> {canonical_gloss: first-alternant IPA}."""
    gt = {}
    with open(IPA_JSONL, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if not r["ipa"]:
                continue
            concept = r.get("canonical_gloss") or r.get("gloss") or ""
            gt.setdefault(r["identifier"], {}).setdefault(concept, r["ipa"].split(",")[0].strip())
    return gt


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--codes", default=",".join(DEFAULT_CODES), help="ISO codes (comma-sep)")
    p.add_argument("--epochs", type=int, default=50)
    args = p.parse_args(argv)
    codes = args.codes.split(",")

    dm = SwadeshDataModule(batch_size=512)
    dm.setup()
    print(f"data [{dm.source}]: {dm.n_lang} languages, {dm.n_concept} concepts")

    # best recipe found by the beam search (r6/r7 regime)
    model = ConditionalVocalicDecoder(
        field_sizes=dm.field_sizes, n_lang=dm.n_lang, n_concept=dm.n_concept,
        d_lang=64, d_concept=64, hidden=384, dropout=0.45, emb_dropout=0.2,
        optimizer="adamw", weight_decay=0.1, lr_schedule="cosine", warmup_frac=0.05,
        lr=7e-3)
    print(f"training best-recipe model for {args.epochs} epochs ...")
    pl.Trainer(max_epochs=args.epochs, accelerator="auto", devices="auto", logger=False,
               enable_checkpointing=False, enable_model_summary=False,
               enable_progress_bar=False).fit(model, dm)

    gt = load_ground_truth()
    eos_kind = dm.fvocab["kind"].get(EOS)
    kind_pos = FIELDS.index("kind")

    # resolve requested codes -> identifiers the model knows
    idents = {}
    for code in codes:
        hit = [i for i in dm.lang_vocab if f"_{code}_" in i]
        if hit:
            idents[code] = hit[0]
        else:
            print(f"  (skipping {code}: not in model)")

    for code, ident in idents.items():
        print(f"\n=== {code}  ({ident})   concept : ground-truth  |  model ===")
        for concept in CONCEPTS:
            if concept not in dm.concept_vocab or concept not in gt.get(ident, {}):
                continue
            li = torch.tensor([dm.lang_vocab[ident]])
            ci = torch.tensor([dm.concept_vocab[concept]])
            segs = model.generate(li, ci, dm.bos, eos_kind, kind_pos=kind_pos)[0]
            print(f"  {concept:8} {gt[ident][concept]:>16}  |  {render_word(segs, dm.fvocab)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
