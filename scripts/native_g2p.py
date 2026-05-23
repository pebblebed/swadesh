#!/usr/bin/env python3
"""Greek & Japanese-Kana grapheme->IPA conversion (Tier 2 of the IPA strategy).

These two native-script lists (rosettaproject_ell_swadesh-1, _jpn_swadesh-1) are
written in fully transparent orthographies -- Modern Greek spelling and hiragana --
so a deterministic rule set converts them to IPA reliably. Both lists are pristine
(pure native script, no romanized synonyms, no multi-word forms, no punctuation),
which is why they are the "easy" Tier-2 scripts. The harder native scripts
(Cyrillic G2P, the Arabic/Hebrew abjads, Han, Thai) are left for later passes.

GREEK (Modern / standard pronunciation), implemented per word:
  1. Vowels: monophthongs α=a ε=e η/ι/υ=i ο/ω=o; the tonos marks stress only
     (no quality change). Vowel digraphs αι=e ει/οι/υι=i ου=u.
  2. αυ/ευ -> [a/e] + [v] before a voiced sound, [f] before a voiceless one or
     word-finally (αυγό=avˈɣo, αυτός=afˈtos).
  3. Velar palatalization before a front vowel (e/i): κ->c γ->ʝ χ->ç
     (και=ce, χέρι=ˈçeri, νύχι=ˈniçi vs νύχτα=ˈnixta).
  4. Voiced-stop digraphs: word-initial μπ/ντ/γκ -> b/d/ɡ; word-medial they are
     prenasalized -> mb/nd/ŋɡ (πέντε=ˈpende, άντρας=ˈandras); γγ=ŋɡ. Affricates
     τσ=t͡s τζ=d͡z. ξ=ks ψ=ps. Double consonants simplify (θάλασσα=ˈθalasa).
  5. σ -> z before a voiced consonant.
  6. Synizesis: an UNstressed i (ι/η/υ/ει/οι) directly before another vowel glides:
     λ/ν before it palatalize and absorb it (κοιλιά=ciˈʎa, ήλιος=ˈiʎos); a velar
     already palatalized absorbs it (χιόνι=ˈçoni); after other consonants it
     surfaces as ç/ʝ/j (καρδιά=karˈðʝa, φωτιά=foˈtça, ποιος=pços). A STRESSED i
     stays a full vowel (δύο=ˈðio, τρία=ˈtria).
  7. Primary stress ˈ placed before the onset of the stressed syllable (one
     intervocalic C to the onset; muta-cum-liquida and s-clusters kept together).
     Monosyllables are left unmarked, per Greek convention.

JAPANESE (hiragana, broad phonetic IPA), per mora:
  - Standard gojūon with the usual allophony: u=ɯ, r=ɾ, し=ɕi ち=t͡ɕi つ=t͡sɯ,
    は=ha ひ=çi ふ=ɸɯ, に=ɲi, the ざ-row as fricatives (ざ=za じ=ʑi ず=zɯ).
  - Sokuon っ geminates the following consonant (はっぱ=happa).
  - Moraic ん assimilates in place to the next consonant (おんな=onna), -> ɴ finally.
  - A bare vowel kana equal to the preceding mora's vowel marks length
    (おおきい=oːkiː, ちいさい=t͡ɕiːsai).
  Japanese pitch accent is not lexically recoverable from kana and is not marked.

Known, documented limitations (faithful, conservative):
  - Greek prenasalized μπ/ντ/γκ medially are transcribed with the nasal retained
    (the careful/dictionary reading); casual speech often denasalizes them.
  - Greek λ/ν are palatalized only by synizesis (before i+V), not the general
    λ/ν-before-[i] allophony.
  - Japanese ざ-row rendered as plain fricatives (the intervocalic realization);
    word-initial affrication ([dz]/[dʑ]) is not marked. None occur word-initially
    in this list.

Run `python scripts/native_g2p.py` to execute the embedded self-test.
"""
import re
import unicodedata

# --- combining marks / multi-codepoint symbols, named to avoid mistyping ---
TIE = "͡"   # combining double inverted breve (affricate tie bar)
LONG = "ː"  # ː length mark
STRESS = "ˈ"  # ˈ primary stress

TS, DZ = "t" + TIE + "s", "d" + TIE + "z"
TSH, DZH = "t" + TIE + "ɕ", "d" + TIE + "ʑ"  # t͡ɕ, d͡ʑ


# ============================ GREEK ============================

# Single vowels -> (quality, stressed?). The tonos marks stress only.
_GR_V = {
    "α": ("a", False), "ά": ("a", True),
    "ε": ("e", False), "έ": ("e", True),
    "η": ("i", False), "ή": ("i", True),
    "ι": ("i", False), "ί": ("i", True),
    "ο": ("o", False), "ό": ("o", True),
    "υ": ("i", False), "ύ": ("i", True),
    "ω": ("o", False), "ώ": ("o", True),
}
# Two-char vowel digraphs -> (quality_or_None, stressed?, is_u_glide?).
# αυ/ευ produce a vowel + a following v/f fricative (handled via U_FRIC token).
_GR_VV = {
    "αι": ("e", False, False), "αί": ("e", True, False), "άι": ("e", True, False),
    "ει": ("i", False, False), "εί": ("i", True, False), "έι": ("i", True, False),
    "οι": ("i", False, False), "οί": ("i", True, False), "όι": ("i", True, False),
    "υι": ("i", False, False), "υί": ("i", True, False),
    "ου": ("u", False, False), "ού": ("u", True, False), "όυ": ("u", True, False),
    "αυ": ("a", False, True), "αύ": ("a", True, True), "άυ": ("a", True, True),
    "ευ": ("e", False, True), "εύ": ("e", True, True), "έυ": ("e", True, True),
}
# Single consonants with a fixed IPA value (no contextual allophony).
_GR_C = {
    "β": "v", "δ": "ð", "ζ": "z", "θ": "θ", "λ": "l", "μ": "m", "ν": "n",
    "π": "p", "ρ": "r", "τ": "t", "φ": "f", "ξ": "ks", "ψ": "ps",
}
# Consonants whose value depends on the following vowel's frontness (tag in pass 2).
_GR_CTAG = {"κ": "k", "γ": "g", "χ": "x", "σ": "s", "ς": "s"}

FRONT = {"e", "i"}
# First IPA char counted as "voiced" for σ->z and αυ/ευ -> v.
VOICED = set("bdɡvðzʝɣmnrlɲŋʎ")
VOICELESS_OBSTR = {"p", "t", "f", "θ", "s", "ks", "ps", TS}
VOICED_OBSTR = {"b", "d", "ɡ", "v", "ð", "z", DZ}
PAL_VELAR = {"c", "ɟ", "ç", "ʝ"}          # already-palatalized velars absorb a glide-i
ONSET_LIQUID = set("rlʎjʝç")               # muta-cum-liquida second member


def _tok(ipa, v=False, stress=False, tag=None):
    return {"ipa": ipa, "v": v, "stress": stress, "tag": tag}


def _greek_tokenize(w):
    """Pass 1: graphemes -> tokens. Vowels resolved (quality+stress); consonants
    tagged where contextual; digraphs/doubles handled; αυ/ευ -> vowel + U_FRIC."""
    out, residual, i, n = [], set(), 0, len(w)
    while i < n:
        c, two = w[i], w[i:i + 2]
        if two in _GR_VV:
            q, st, uglide = _GR_VV[two]
            out.append(_tok(q, v=True, stress=st))
            if uglide:
                out.append(_tok(None, tag="U"))   # the υ -> v/f, resolved in pass 2
            i += 2
            continue
        if two in ("μπ", "ντ", "γκ", "γγ", "γχ", "γξ", "τσ", "τζ"):
            tagmap = {"μπ": "MB", "ντ": "ND", "γκ": "GK", "γγ": "GG",
                      "γχ": "GX", "γξ": "GKS", "τσ": TS, "τζ": DZ}
            t = tagmap[two]
            if t in (TS, DZ):
                out.append(_tok(t))
            else:
                out.append(_tok(None, tag=t))
            i += 2
            continue
        if c in _GR_C and i + 1 < n and w[i + 1] == c:   # double consonant -> single
            out.append(_tok(_GR_C[c]))
            i += 2
            continue
        if c in _GR_CTAG and i + 1 < n and w[i + 1] == c:  # κκ/σσ etc. -> single (tagged)
            out.append(_tok(None, tag=_GR_CTAG[c]))
            i += 2
            continue
        if c in _GR_V:
            q, st = _GR_V[c]
            out.append(_tok(q, v=True, stress=st))
            i += 1
            continue
        if c in _GR_C:
            out.append(_tok(_GR_C[c]))
            i += 1
            continue
        if c in _GR_CTAG:
            out.append(_tok(None, tag=_GR_CTAG[c]))
            i += 1
            continue
        residual.add(c)
        out.append(_tok(c))
        i += 1
    return out, residual


def _next_front(toks, i):
    nxt = toks[i + 1] if i + 1 < len(toks) else None
    return bool(nxt and nxt["v"] and nxt["ipa"] in FRONT)


def _next_voiced(toks, i):
    """Is the token after i a voiced sound (vowel or voiced consonant)?"""
    nxt = toks[i + 1] if i + 1 < len(toks) else None
    if nxt is None:
        return False
    if nxt["v"]:
        return True
    return bool(nxt["ipa"]) and nxt["ipa"][0] in VOICED


def _greek_resolve(toks):
    """Pass 2: resolve tagged consonants (palatalization, prenasalization, σ->z).
    A medial μπ/ντ/γκ/γγ expands to nasal+stop, the stop flagged `pren` so stress
    later treats the prenasalized cluster as one onset. αυ/ευ's υ (tag "U") is
    resolved in a second sweep, once the following consonant's value is known."""
    out = []
    for i, t in enumerate(toks):
        tag = t["tag"]
        if tag is None or tag == "U":
            out.append(t)
            continue
        front = _next_front(toks, i)
        initial = (i == 0)
        if tag == "k":
            out.append(_tok("c" if front else "k"))
        elif tag == "g":
            out.append(_tok("ʝ" if front else "ɣ"))
        elif tag == "x":
            out.append(_tok("ç" if front else "x"))
        elif tag == "s":
            voiced_next = (i + 1 < len(toks) and not toks[i + 1]["v"]
                           and toks[i + 1]["ipa"] and toks[i + 1]["ipa"][0] in VOICED)
            out.append(_tok("z" if voiced_next else "s"))
        elif tag in ("MB", "ND", "GK", "GG", "GX", "GKS"):
            stop = {"MB": "b", "ND": "d", "GK": "ɟ" if front else "ɡ",
                    "GG": "ɟ" if front else "ɡ", "GX": "ç" if front else "x",
                    "GKS": "ks"}[tag]
            nasal = {"MB": "m", "ND": "n", "GK": "ŋ", "GG": "ŋ",
                     "GX": "ŋ", "GKS": "ŋ"}[tag]
            if stop == "ɟ":                           # palatal stop -> palatal nasal
                nasal = "ɲ"
            if initial and tag in ("MB", "ND", "GK"):
                out.append(_tok(stop))
            else:
                out.append(_tok(nasal))
                st = _tok(stop)
                st["pren"] = True
                out.append(st)
        else:
            out.append(t)
    for i, t in enumerate(out):                       # second sweep: αυ/ευ -> v/f
        if t["tag"] == "U":
            t["tag"] = None
            t["ipa"] = "v" if _next_voiced(out, i) else "f"
            t["coda"] = True                          # a diphthong coda, never an onset
    return out


def _greek_synizesis(toks):
    """Pass 3: an unstressed i directly before another vowel becomes a glide and
    palatalizes/merges with the preceding consonant."""
    out = []
    i = 0
    while i < len(toks):
        t = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if (t["v"] and t["ipa"] == "i" and not t["stress"]
                and nxt is not None and nxt["v"]):
            prev = out[-1] if out else None
            if prev is None or prev["v"]:
                out.append(_tok("j"))                       # word-initial / hiatus
            elif prev["ipa"] == "l":
                prev["ipa"] = "ʎ"                            # absorbed
            elif prev["ipa"] == "n":
                prev["ipa"] = "ɲ"                            # absorbed
            elif prev["ipa"] == "m":
                out.append(_tok("ɲ"))                        # mι -> mɲ
            elif prev["ipa"] == "r":
                out.append(_tok("j"))
            elif prev["ipa"] in PAL_VELAR:
                pass                                         # absorbed into c/ç/ʝ/ɟ
            elif prev["ipa"] in VOICELESS_OBSTR:
                out.append(_tok("ç"))
            elif prev["ipa"] in VOICED_OBSTR:
                out.append(_tok("ʝ"))
            else:
                out.append(_tok("j"))
            i += 1
            continue
        out.append(t)
        i += 1
    return out


def _greek_stress(toks):
    """Pass 4: render, inserting ˈ before the onset of the stressed syllable."""
    nv = sum(1 for t in toks if t["v"])
    sidx = next((i for i, t in enumerate(toks) if t["v"] and t["stress"]), None)
    mark = sidx is not None and nv > 1     # monosyllables left unmarked
    onset = sidx
    if mark:
        # walk left over the onset consonants of the stressed syllable
        j = sidx - 1
        if j >= 0 and not toks[j]["v"]:
            onset = j                       # the immediate onset consonant
            k = j - 1
            while k >= 0 and not toks[k]["v"]:
                left = toks[onset]["ipa"]
                cand = toks[k]["ipa"]
                # keep a cluster together: a prenasalized stop pulls in its nasal,
                # plus obstruent+liquid (muta cum liquida) and s/z + consonant.
                if toks[onset].get("pren") and cand in ("m", "n", "ŋ", "ɲ"):
                    onset = k
                elif left and left[0] in ONSET_LIQUID:
                    onset = k
                elif cand in ("s", "z"):
                    onset = k
                elif (left and left[0] in "ptkc" and cand in ("f", "θ", "x", "ç")
                      and not toks[k].get("coda")):
                    onset = k                   # fricative+stop onset (φτ, χτ): ˈftino
                else:
                    break
                k -= 1
    parts = []
    for i, t in enumerate(toks):
        if mark and i == onset:
            parts.append(STRESS)
        parts.append(t["ipa"])
    return "".join(parts)


def greek_to_ipa(word):
    toks, residual = _greek_tokenize(word)
    toks = _greek_resolve(toks)
    toks = _greek_synizesis(toks)
    return _greek_stress(toks), residual


# ============================ JAPANESE (kana) ============================

_KANA = {
    "あ": "a", "い": "i", "う": "ɯ", "え": "e", "お": "o",
    "か": "ka", "き": "ki", "く": "kɯ", "け": "ke", "こ": "ko",
    "が": "ɡa", "ぎ": "ɡi", "ぐ": "ɡɯ", "げ": "ɡe", "ご": "ɡo",
    "さ": "sa", "し": "ɕi", "す": "sɯ", "せ": "se", "そ": "so",
    "ざ": "za", "じ": "ʑi", "ず": "zɯ", "ぜ": "ze", "ぞ": "zo",
    "た": "ta", "ち": TSH + "i", "つ": TS + "ɯ", "て": "te", "と": "to",
    "だ": "da", "ぢ": DZH + "i", "づ": DZ + "ɯ", "で": "de", "ど": "do",
    "な": "na", "に": "ɲi", "ぬ": "nɯ", "ね": "ne", "の": "no",
    "は": "ha", "ひ": "çi", "ふ": "ɸɯ", "へ": "he", "ほ": "ho",
    "ば": "ba", "び": "bi", "ぶ": "bɯ", "べ": "be", "ぼ": "bo",
    "ぱ": "pa", "ぴ": "pi", "ぷ": "pɯ", "ぺ": "pe", "ぽ": "po",
    "ま": "ma", "み": "mi", "む": "mɯ", "め": "me", "も": "mo",
    "や": "ja", "ゆ": "jɯ", "よ": "jo",
    "ら": "ra", "り": "ri", "る": "rɯ", "れ": "re", "ろ": "ro",
    "わ": "wa", "を": "o",
}
_BARE_VOWEL = set("あいうえお")
_GEMINATE, _MORAIC_N = "っ", "ん"
# Japanese r is a tap; rewrite r -> ɾ at the very end (kept as 'r' in the table
# so the gemination/length logic stays readable).
_R_FIX = str.maketrans({"r": "ɾ"})


def _n_assimilate(next_ipa):
    """Place of the moraic nasal ん given the next mora's leading IPA."""
    if not next_ipa:
        return "ɴ"                                  # word-final
    c = next_ipa[0]
    if c in "pbm":
        return "m"
    if c in "kɡ":
        return "ŋ"
    if c in ("t", "d", "n", "s", "z", "r"):
        return "n"
    if c in ("ɕ", "ʑ", "ɲ", "j"):
        return "ɲ"
    return "ɴ"                                       # vowels, h, w, ɸ, ç ...


def kana_to_ipa(word):
    # Build a flat list of mora IPA strings, resolving っ and ん.
    moras, residual = [], set()
    i, n = 0, len(word)
    while i < n:
        c = word[i]
        if c == _GEMINATE:
            nxt = word[i + 1] if i + 1 < n else ""
            nipa = _KANA.get(nxt, "")
            if nipa and nipa[0] not in "aiɯeo":
                moras.append(nipa[0])               # gemination = held first C
            i += 1
            continue
        if c == _MORAIC_N:
            nxt = word[i + 1] if i + 1 < n else ""
            moras.append(_n_assimilate(_KANA.get(nxt, "")))
            i += 1
            continue
        if c in _KANA:
            moras.append(_KANA[c])
            i += 1
            continue
        residual.add(c)
        moras.append(c)
        i += 1

    # Vowel length: re-walk the kana stream alongside `moras`; a bare-vowel kana
    # equal to the previous mora's final vowel lengthens it instead of repeating.
    out, prev_vowel, mi = [], None, 0
    for c in word:
        if c in (_GEMINATE, _MORAIC_N) or c not in _KANA:
            # consonantal / special mora: emit and reset the vowel context
            out.append(moras[mi])
            prev_vowel = None
            mi += 1
            continue
        ipa = moras[mi]
        if c in _BARE_VOWEL and prev_vowel is not None and ipa == prev_vowel:
            out.append(LONG)                        # lengthen the preceding vowel
        else:
            out.append(ipa)
            prev_vowel = ipa[-1]
        mi += 1
    return "".join(out).translate(_R_FIX), residual


# ============================ public API ============================

_PAREN = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_SEG = re.compile(r"[,/;]")


def to_ipa(transcription, script):
    """Convert a normalized native-script transcription to IPA.

    `script` is "Greek" or "Kana" (matching transcription_systems.tsv's
    native:<Script> tag). Returns (ipa, residual_set); residual holds any source
    character with no mapping (expected empty for these two clean lists)."""
    conv = greek_to_ipa if script == "Greek" else kana_to_ipa
    text = _PAREN.sub(" ", unicodedata.normalize("NFC", transcription).lower())
    residual, segments = set(), []
    for seg in _SEG.split(text):
        words = []
        for wd in seg.split():
            ipa, res = conv(wd)
            residual |= res
            if ipa:
                words.append(ipa)
        if words:
            segments.append(" ".join(words))
    return ", ".join(segments), residual


# ============================ self-test ============================
# Gold forms derived by hand from Modern Greek phonology and standard Japanese
# (hiragana) phonology. Covers palatalization, αυ/ευ, prenasalization, synizesis,
# σ->z, stress, double-consonant simplification (Greek); the gojūon allophony,
# gemination, moraic-n assimilation, and vowel length (Japanese).
_TESTS = [
    # --- Greek: vowels, stress, basic consonants ---
    ("Greek", "όλα", "ˈola"), ("Greek", "ζώο", "ˈzoo"),
    ("Greek", "κακό", "kaˈko"), ("Greek", "πλάτη", "ˈplati"),
    ("Greek", "εγώ", "eˈɣo"), ("Greek", "εσύ", "eˈsi"),
    ("Greek", "μεγάλο", "meˈɣalo"), ("Greek", "πουλί", "puˈli"),
    ("Greek", "δάσος", "ˈðasos"), ("Greek", "θάλασσα", "ˈθalasa"),
    ("Greek", "τέσσερα", "ˈtesera"), ("Greek", "κόκκαλο", "ˈkokalo"),
    # --- Greek: velar palatalization before front vowels ---
    ("Greek", "και", "ce"), ("Greek", "χέρι", "ˈçeri"),
    ("Greek", "νύχι", "ˈniçi"), ("Greek", "νύχτα", "ˈnixta"),
    ("Greek", "κίτρινο", "ˈcitrino"), ("Greek", "κόκκινο", "ˈkocino"),
    ("Greek", "γελάω", "ʝeˈlao"), ("Greek", "γυρίζω", "ʝiˈrizo"),
    # --- Greek: αυ/ευ ---
    ("Greek", "αυτός", "afˈtos"), ("Greek", "αυγό", "avˈɣo"),
    ("Greek", "μαύρο", "ˈmavro"), ("Greek", "αίμα", "ˈema"),
    # --- Greek: prenasalized voiced-stop digraphs + affricates ---
    ("Greek", "πέντε", "ˈpende"), ("Greek", "άντρας", "ˈandras"),
    ("Greek", "δόντι", "ˈðondi"), ("Greek", "φεγγάρι", "feˈŋɡari"),
    ("Greek", "δαγκώνω", "ðaˈŋɡono"), ("Greek", "κολυμπώ", "koliˈmbo"),
    ("Greek", "ξέρω", "ˈksero"), ("Greek", "ψάρι", "ˈpsari"),
    # --- Greek: synizesis (unstressed i + vowel) vs stressed i ---
    ("Greek", "κοιλιά", "ciˈʎa"), ("Greek", "ήλιος", "ˈiʎos"),
    ("Greek", "χιόνι", "ˈçoni"), ("Greek", "καρδιά", "karˈðʝa"),
    ("Greek", "ποιος", "pços"), ("Greek", "φωτιά", "foˈtça"),
    ("Greek", "δύο", "ˈðio"), ("Greek", "τρία", "ˈtria"),
    ("Greek", "γυναίκα", "ʝiˈneka"),
    # --- Greek: onset clustering for stress (fricative+stop, palatal nasal) ---
    ("Greek", "φτύνω", "ˈftino"), ("Greek", "λεπτό", "lepˈto"),
    ("Greek", "στρογγυλό", "stroɲɟiˈlo"), ("Greek", "σπρώχνω", "ˈsproxno"),
    # --- Japanese: basic gojūon + allophony ---
    ("Kana", "とり", "toɾi"), ("Kana", "いぬ", "inɯ"),
    ("Kana", "しぬ", "ɕinɯ"), ("Kana", "ち", "t͡ɕi"),
    ("Kana", "つめ", "t͡sɯme"), ("Kana", "ひ", "çi"),
    ("Kana", "ふたつ", "ɸɯtat͡sɯ"), ("Kana", "にく", "ɲikɯ"),
    ("Kana", "なに", "naɲi"), ("Kana", "みず", "mizɯ"),
    ("Kana", "ひざ", "çiza"), ("Kana", "だれ", "daɾe"),
    ("Kana", "やま", "jama"), ("Kana", "すわる", "sɯwaɾɯ"),
    # --- Japanese: gemination, moraic n, vowel length ---
    ("Kana", "はっぱ", "happa"), ("Kana", "おんな", "onna"),
    ("Kana", "おおきい", "oːkiː"), ("Kana", "ちいさい", "t͡ɕiːsai"),
    ("Kana", "あたらしい", "ataɾaɕiː"), ("Kana", "あめ", "ame"),
]


def selftest():
    fails = 0
    for script, word, want in _TESTS:
        got, _ = to_ipa(word, script)
        want = unicodedata.normalize("NFC", want)
        got = unicodedata.normalize("NFC", got)
        if got != want:
            fails += 1
            print(f"FAIL {script} {word!r}: got {got!r}  want {want!r}")
    total = len(_TESTS)
    print(f"native_g2p self-test: {total - fails}/{total} passed")
    return fails


if __name__ == "__main__":
    import sys
    sys.exit(1 if selftest() else 0)
