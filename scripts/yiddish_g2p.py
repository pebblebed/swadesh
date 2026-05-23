#!/usr/bin/env python3
"""Yiddish (Hebrew script, YIVO orthography) -> IPA (Tier 2 of the IPA strategy).

Unlike the Arabic/Persian abjads, Yiddish WRITES its vowels (the alef/ayin/vov/
yud system), so standard YIVO spelling maps to IPA by a deterministic rule set.
Hebrew text is stored in logical (reading) order, so we just iterate the string.

Per word:
  - Vowels: אַ (alef+pasekh)=a, אָ (alef+komets)=ɔ, bare א = silent (shtumer alef);
    ע (ayin)=ɛ; ו (vov)=u (וּ melupm = u); יִ (yud+khirik)=i.
  - Diphthong ligatures: ײ (tsvey yudn)=ej, ײַ (+pasekh)=aj, ױ (vov-yud)=ɔj.
  - Glide: bare י = /j/ before a vowel letter (יאָגן=jɔgn, יענער=jɛnɛr), else /i/
    (בילן=biln, קני=kni).
  - Consonants: בּ=b בֿ=v (bare ב=b); פּ=p פֿ=f (bare פ=f), final ף=f; כּ=k כֿ=x
    (bare כ=x), final ך=x; װ (tsvey vovn)=v; ג=g ד=d ה=h ז=z ט=t ל=l מ/ם=m נ/ן=n
    ס=s צ/ץ=t͡s ק=k ר=r ש=ʃ; ח=x, ת=s (Hebrew-origin). Affricates: טש=t͡ʃ זש=ʒ
    דז=d͡z דזש=d͡ʒ.
  - LOSHN-KOYDESH (Hebrew/Aramaic-origin words) are spelled consonantally, NOT by
    the phonetic system (often with unwritten vowels), so the rules fail on them.
    There are only five in this list; they are given directly in HEBREW
    (חיה=xajɛ ים=jam מורא=mɔjrɛ לבֿנה=lɛvɔnɛ סך=sax).

Broad phonemic, no vowel reduction (Yiddish reduces unstressed vowels to ə, but
stress is unmarked -- consistent with the Slavic/Cyrillic handlers).

Run `python scripts/yiddish_g2p.py` for the embedded self-test.
"""
import unicodedata

TIE = "͡"
PASEKH, KOMETS, KHIRIK = "ַ", "ָ", "ִ"
DAGESH, ROFE = "ּ", "ֿ"
TSH, DZH, DZ, TS = "t" + TIE + "ʃ", "d" + TIE + "ʒ", "d" + TIE + "z", "t" + TIE + "s"

FIXED = {
    "ג": "ɡ", "ד": "d", "ה": "h", "ז": "z", "ח": "x", "ט": "t", "ל": "l",
    "מ": "m", "ם": "m", "נ": "n", "ן": "n", "ס": "s", "צ": TS, "ץ": TS,
    "ק": "k", "ר": "r", "ש": "ʃ", "ך": "x", "ף": "f", "ת": "s",
}
# letters whose value depends on a following dagesh (stop) vs rofe (fricative)
_DR = {"ב": ("b", "v"), "כ": ("k", "x"), "פ": ("p", "f")}
_DR_BARE = {"ב": "b", "כ": "x", "פ": "f"}      # bare (unpointed) default
VOWEL_LETTERS = set("אעוױײ")                    # a following one makes yud a glide
_MARKS = {PASEKH, KOMETS, KHIRIK, DAGESH, ROFE}

# Loshn-koydesh (Hebrew-origin) words: spelled consonantally, given directly.
HEBREW = {"חיה": "xajɛ", "ים": "jam", "מורא": "mɔjrɛ", "לבֿנה": "lɛvɔnɛ", "סך": "sax"}


def _word_to_ipa(w):
    out, residual, i, n = [], set(), 0, len(w)
    while i < n:
        c = w[i]
        nxt = w[i + 1] if i + 1 < n else ""
        if w[i:i + 3] == "דזש":
            out.append(DZH); i += 3; continue
        two = w[i:i + 2]
        if two == "טש":
            out.append(TSH); i += 2; continue
        if two == "זש":
            out.append("ʒ"); i += 2; continue
        if two == "דז":
            out.append(DZ); i += 2; continue
        if c == "א":
            if nxt == PASEKH:
                out.append("a"); i += 2
            elif nxt == KOMETS:
                out.append("ɔ"); i += 2
            else:
                i += 1                          # shtumer alef: silent
            continue
        if c == "ײ":
            out.append("aj" if nxt == PASEKH else "ej")
            i += 2 if nxt == PASEKH else 1
            continue
        if c == "װ":
            out.append("v"); i += 1; continue
        if c == "ױ":
            out.append("ɔj"); i += 1; continue
        if c == "ו":
            out.append("u"); i += 2 if nxt == DAGESH else 1; continue
        if c == "ע":
            out.append("ɛ"); i += 1; continue
        if c == "י":
            if nxt == KHIRIK:
                out.append("i"); i += 2
            else:
                out.append("j" if nxt in VOWEL_LETTERS else "i"); i += 1
            continue
        if c in _DR:
            if nxt == DAGESH:
                out.append(_DR[c][0]); i += 2
            elif nxt == ROFE:
                out.append(_DR[c][1]); i += 2
            else:
                out.append(_DR_BARE[c]); i += 1
            continue
        if c in FIXED:
            out.append(FIXED[c]); i += 1; continue
        if c in _MARKS:
            i += 1; continue                    # stray point: skip
        residual.add(c); out.append(c); i += 1
    return "".join(out), residual


def to_ipa(transcription):
    """Convert a normalized Yiddish transcription to IPA. Handles multi-word forms
    (split on space). Returns (ipa, residual_set)."""
    residual, words = set(), []
    for w in unicodedata.normalize("NFC", transcription).split():
        if w in HEBREW:
            words.append(HEBREW[w])
            continue
        ipa, res = _word_to_ipa(w)
        residual |= res
        if ipa:
            words.append(ipa)
    return " ".join(words), residual


# ------------------------------- self-test --------------------------------
_TESTS = [
    ("אַלע", "alɛ"), ("בײַ", "baj"), ("שלעכט", "ʃlɛxt"), ("בױך", "bɔjx"),
    ("גרױס", "ɡrɔjs"), ("פֿױגל", "fɔjɡl"), ("שװאַרץ", "ʃvart͡s"),
    ("בלאָזן", "blɔzn"), ("קינד", "kind"), ("אױג", "ɔjɡ"), ("אײ", "ej"),
    ("מיך", "mix"), ("איך", "ix"), ("יאָגן", "jɔɡn"), ("יענער", "jɛnɛr"),
    ("פֿליִען", "fliɛn"), ("צוריק", "t͡surik"), ("קאָפּ", "kɔp"),
    ("שלאָפֿן", "ʃlɔfn"), ("מענטש", "mɛnt͡ʃ"), ("האַלדז", "hald͡z"),
    ("צװײ", "t͡svej"), ("דרײַ", "draj"), ("שנײ", "ʃnej"), ("פֿרױ", "frɔj"),
    ("װאַסער", "vasɛr"), ("אױער", "ɔjɛr"), ("בילן", "biln"), ("קני", "kni"),
    ("נעפּל", "nɛpl"), ("שטײן", "ʃtejn"), ("זון", "zun"),
    # Hebrew-origin overrides + multi-word
    ("חיה", "xajɛ"), ("מורא", "mɔjrɛ"), ("לבֿנה", "lɛvɔnɛ"),
    ("אַ סך", "a sax"), ("זיך שלאָגן", "zix ʃlɔɡn"),
]


def selftest():
    fails = 0
    for src, want in _TESTS:
        got, _ = to_ipa(src)
        got, want = unicodedata.normalize("NFC", got), unicodedata.normalize("NFC", want)
        if got != want:
            fails += 1
            print(f"FAIL {src!r}: got {got!r}  want {want!r}")
    print(f"yiddish_g2p self-test: {len(_TESTS) - fails}/{len(_TESTS)} passed")
    return fails


if __name__ == "__main__":
    import sys
    sys.exit(1 if selftest() else 0)
