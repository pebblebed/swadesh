"""Conditional vocalic decoder for the Rosetta Swadesh corpus.

Learn latent representations of each language and each concept, then decode the
phonetic form -- a sequence of articulatory feature bundles -- conditioned on
both (see TODO 'MODELING DIRECTION' and notes/). Language relatedness is read off
distances between the learned language embeddings.

Submodules are imported lazily (they pull in torch / lightning); `model.data` is
pure-python and torch-free so the vocab / feature logic stays unit-testable.
"""
