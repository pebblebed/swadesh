#!/usr/bin/env python3
"""Parse the romanization line that some native-script lists carry, into IPA.

A few native-script lists ship a Latin/IPA romanization alongside the native
script, one per gloss. Converting THAT line sidesteps the hard script problem
entirely (and, for Thai, the mojibake in the native-script line). This is the
high-confidence Tier-2 path: the SOURCE already did the phonetic analysis.

  arabic_to_ipa : arb (Standard Arabic) already provides a full IPA romanization
    (kullu, ramaːdun, batˁnun, ʕusˁfuːratun, -ʤiːʔ-) -> pass through, only folding
    the tie-less affricate letters (ʤ->d͡ʒ etc.) to the corpus's tie-bar form.
  thai_to_ipa   : tha provides a Latin romanization with 2-digit Chao tone
    numbers (thang55, khi:41thau41) -> map digraphs (th->tʰ kh->kʰ ph->pʰ
    ch->t͡ɕʰ ng->ŋ) and vowels (å->ɔ æ->ɛ y->ɯ ø->ɤ); ':' -> length ː; each tone
    digit -> a Chao tone letter (5->˥ 4->˦ 3->˧ 2->˨ 1->˩). Syllables are
    self-delimiting because every one ends in its tone digits.

NOT handled here (deferred): the arb/pes/pbt Arabic-SCRIPT lines and the cmn Han
script have no usable romanization, and pes/pbt are abjads (short vowels unwritten).

Run `python scripts/romanize.py` for the embedded self-test.
"""
import unicodedata

TIE = "͡"

# --- Arabic: the romanization is already IPA; fold tie-less affricate letters ---
_ARB_FIX = {"ʤ": "d" + TIE + "ʒ", "ʧ": "t" + TIE + "ʃ",
            "ʦ": "t" + TIE + "s", "ʣ": "d" + TIE + "z"}


def arabic_to_ipa(text):
    t = unicodedata.normalize("NFC", text)
    for k, v in _ARB_FIX.items():
        t = t.replace(k, v)
    return t, set()


# --- Thai romanization -> IPA ---
_TH_DIGRAPH = {"th": "tʰ", "kh": "kʰ", "ph": "pʰ", "ch": "t" + TIE + "ɕʰ", "ng": "ŋ"}
_TH_C = {"k": "k", "c": "t" + TIE + "ɕ", "t": "t", "n": "n", "p": "p", "m": "m",
         "r": "r", "l": "l", "w": "w", "s": "s", "h": "h", "d": "d", "b": "b",
         "j": "j", "f": "f", "g": "ɡ", "ʔ": "ʔ"}
_TH_V = {"a": "a", "i": "i", "u": "u", "e": "e", "o": "o",
         "å": "ɔ", "æ": "ɛ", "y": "ɯ", "ø": "ɤ"}


def _tone(d):
    return chr(0x02E5 + (5 - int(d)))      # 5->˥(U+02E5) ... 1->˩(U+02E9)


def thai_to_ipa(text):
    residual, words = set(), []
    for word in unicodedata.normalize("NFC", text).split():
        o, i, n = [], 0, len(word)
        while i < n:
            two = word[i:i + 2].lower()
            c = word[i].lower()
            if two in _TH_DIGRAPH:
                o.append(_TH_DIGRAPH[two]); i += 2
            elif c in "12345":
                j = i
                while j < n and word[j] in "12345":
                    j += 1
                o.append("".join(_tone(d) for d in word[i:j])); i = j
            elif c == ":":
                o.append("ː"); i += 1
            elif c in _TH_C:
                o.append(_TH_C[c]); i += 1
            elif c in _TH_V:
                o.append(_TH_V[c]); i += 1
            else:
                residual.add(word[i]); o.append(word[i]); i += 1
        words.append("".join(o))
    return " ".join(words), residual


# ------------------------------- self-test --------------------------------
_TESTS = [
    # Thai (romanization line; tones as Chao letters)
    ("tha", "thang55", "tʰaŋ˥˥"), ("tha", "læ55", "lɛ˥˥"),
    ("tha", "sat22", "sat˨˨"), ("tha", "lang24", "laŋ˨˦"),
    ("tha", "khi:41thau41", "kʰiː˦˩tʰau˦˩"), ("tha", "chua41", "t͡ɕʰua˦˩"),
    ("tha", "plyak41", "plɯak˦˩"), ("tha", "phrå55wa:41", "pʰrɔ˥˥waː˦˩"),
    ("tha", "thå:ng55", "tʰɔːŋ˥˥"), ("tha", "jai22", "jai˨˨"),
    ("tha", "kra22du:k22", "kra˨˨duːk˨˨"), ("tha", "ha:i24cai33", "haːi˨˦t͡ɕai˧˧"),
    ("tha", "me:k41", "meːk˦˩"), ("tha", "nok55", "nok˥˥"),
    # Arabic (already IPA; only the tie-less affricate is folded)
    ("arb", "ramaːdun", "ramaːdun"), ("arb", "batˁnun", "batˁnun"),
    ("arb", "ʕusˁfuːratun", "ʕusˁfuːratun"), ("arb", "-ʤiːʔ-", "-d͡ʒiːʔ-"),
    ("arb", "kabiːrun", "kabiːrun"),
]


def selftest():
    fails = 0
    for lang, src, want in _TESTS:
        got, _ = (thai_to_ipa if lang == "tha" else arabic_to_ipa)(src)
        want = unicodedata.normalize("NFC", want)
        got = unicodedata.normalize("NFC", got)
        if got != want:
            fails += 1
            print(f"FAIL {lang} {src!r}: got {got!r}  want {want!r}")
    print(f"romanize self-test: {len(_TESTS) - fails}/{len(_TESTS)} passed")
    return fails


if __name__ == "__main__":
    import sys
    sys.exit(1 if selftest() else 0)
